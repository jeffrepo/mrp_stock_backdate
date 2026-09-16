from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMrpStockBackdate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tz="America/Guatemala"))
        cls.stock = cls.env.ref("stock.stock_location_stock")
        cls.supplier = cls.env.ref("stock.stock_location_suppliers")
        cls.customer = cls.env.ref("stock.stock_location_customers")
        cls.uom = cls.env.ref("uom.product_uom_unit")
        cls.month_ago = fields.Datetime.now() - relativedelta(months=1)
        cls.year_ago = fields.Datetime.now() - relativedelta(years=1)

        accounts = cls.env["account.account"].create([
            {
                "name": name,
                "code": code,
                "user_type_id": cls.env.ref("account.data_account_type_current_assets").id,
                "company_id": cls.env.company.id,
            }
            for name, code in (
                ("Backdate valuation", "BD100"),
                ("Backdate input", "BD200"),
                ("Backdate output", "BD300"),
            )
        ])
        journal = cls.env["account.journal"].create({
            "name": "Backdate stock", "code": "BDST", "type": "general",
            "company_id": cls.env.company.id,
        })
        cls.category = cls.env["product.category"].create({
            "name": "Backdate products",
            "property_cost_method": "standard",
            "property_valuation": "real_time",
            "property_stock_journal": journal.id,
            "property_stock_valuation_account_id": accounts[0].id,
            "property_stock_account_input_categ_id": accounts[1].id,
            "property_stock_account_output_categ_id": accounts[2].id,
        })
        cls.component, cls.finished, cls.byproduct = cls.env["product.product"].create([
            {
                "name": name, "type": "product", "categ_id": cls.category.id,
                "standard_price": cost, "uom_id": cls.uom.id,
                "uom_po_id": cls.uom.id,
            }
            for name, cost in (("Component", 5), ("Finished", 10), ("Byproduct", 1))
        ])
        cls.bom = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.finished.product_tmpl_id.id,
            "product_qty": 1, "product_uom_id": cls.uom.id,
            "consumption": "flexible",
            "bom_line_ids": [(0, 0, {
                "product_id": cls.component.id, "product_qty": 2,
                "product_uom_id": cls.uom.id,
            })],
        })
        cls.env["stock.quant"]._update_available_quantity(cls.component, cls.stock, 100)

    def _production(self, date, quantity=1, ready=True, bom=None):
        with Form(self.env["mrp.production"]) as form:
            form.product_id = self.finished
            form.bom_id = bom or self.bom
            form.product_qty = quantity
            form.date_planned_start = date
        production = form.save()
        production.action_confirm()
        if ready:
            production.qty_producing = quantity
            production._set_qty_producing()
        return production

    def _assert_dates(self, production, expected):
        self.assertEqual(production.state, "done")
        moves = (production.move_raw_ids | production.move_finished_ids).filtered(
            lambda move: move.state == "done" and move.quantity_done
        )
        self.assertTrue(moves)
        local_date = fields.Datetime.context_timestamp(production, expected).date()
        for move in moves:
            self.assertEqual(move.date, expected)
            self.assertTrue(move.move_line_ids)
            self.assertEqual(set(move.move_line_ids.mapped("date")), {expected})
            self.assertTrue(move.stock_valuation_layer_ids)
            for layer in move.stock_valuation_layer_ids.filtered("quantity"):
                self.assertEqual(layer.create_date, expected)
                self.assertGreater(layer.mrp_recorded_at, expected)
                if self.category.property_valuation == "real_time":
                    self.assertEqual(layer.account_move_id.state, "posted")
                    self.assertEqual(layer.account_move_id.date, local_date)
        self.assertGreater(production.date_finished, expected)

    def test_one_month_ago(self):
        production = self._production(self.month_ago)
        production.button_mark_done()
        self._assert_dates(production, self.month_ago)
        self.assertEqual(self.component.qty_available, 98)
        self.assertEqual(self.finished.qty_available, 1)

    def test_one_year_ago_and_historical_reports(self):
        production = self._production(self.year_ago)
        production.button_mark_done()
        self._assert_dates(production, self.year_ago)
        before = self.finished.with_context(to_date=self.year_ago - timedelta(seconds=1))
        after = self.finished.with_context(to_date=self.year_ago + timedelta(seconds=1))
        self.assertEqual(before.qty_available, 0)
        self.assertEqual(after.qty_available, 1)
        self.assertEqual(before.value_svl, 0)
        self.assertEqual(after.value_svl, 10)

    def test_batch_keeps_each_production_date(self):
        older = self._production(self.year_ago)
        newer = self._production(self.month_ago)
        (older | newer).button_mark_done()
        self._assert_dates(older, self.year_ago)
        self._assert_dates(newer, self.month_ago)

    def test_accounting_uses_local_day_across_midnight(self):
        backdate = self.year_ago.replace(hour=2, minute=0, second=0)
        production = self._production(backdate)
        production.button_mark_done()
        self._assert_dates(production, backdate)
        entries = production.move_raw_ids.stock_valuation_layer_ids.account_move_id
        self.assertEqual(set(entries.mapped("date")), {(backdate - timedelta(days=1)).date()})

    def test_future_schedule_uses_actual_posting_date(self):
        production = self._production(fields.Datetime.now() + timedelta(days=30))
        started = fields.Datetime.now()
        production.button_mark_done()
        moves = production.move_raw_ids | production.move_finished_ids
        for move in moves:
            self.assertGreaterEqual(move.date, started)
            self.assertLessEqual(move.date, fields.Datetime.now())
        self.assertFalse(any(moves.stock_valuation_layer_ids.mapped("mrp_recorded_at")))

    def test_confirmation_does_not_consume(self):
        production = self._production(self.year_ago, ready=False)
        self.assertNotEqual(production.state, "done")
        self.assertFalse(production.move_raw_ids.stock_valuation_layer_ids)
        self.assertEqual(self.component.qty_available, 100)

    def test_immediate_production_wizard(self):
        production = self._production(self.month_ago, ready=False)
        action = production.button_mark_done()
        self.assertEqual(action["res_model"], "mrp.immediate.production")
        self.assertFalse(production.move_raw_ids.stock_valuation_layer_ids)
        wizard = Form(self.env[action["res_model"]].with_context(action["context"])).save()
        wizard.process()
        self._assert_dates(production, self.month_ago)

    def test_partial_production_and_backorder(self):
        production = self._production(self.year_ago, quantity=2, ready=False)
        production.qty_producing = 1
        production._set_qty_producing()
        action = production.button_mark_done()
        self.assertEqual(action["res_model"], "mrp.production.backorder")
        wizard = Form(self.env[action["res_model"]].with_context(action["context"])).save()
        wizard.action_backorder()
        backorder = production.procurement_group_id.mrp_production_ids - production
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.date_planned_start, self.year_ago)
        self._assert_dates(production, self.year_ago)
        original_layers = production.move_raw_ids.stock_valuation_layer_ids
        original_dates = original_layers.mapped("create_date")
        backorder.date_planned_start = self.month_ago
        backorder.qty_producing = 1
        backorder._set_qty_producing()
        backorder.button_mark_done()
        self._assert_dates(backorder, self.month_ago)
        self.assertEqual(original_layers.mapped("create_date"), original_dates)

    def test_byproducts(self):
        bom = self.bom.copy({"byproduct_ids": [(0, 0, {
            "product_id": self.byproduct.id, "product_qty": 1,
            "product_uom_id": self.uom.id,
        })]})
        production = self._production(self.month_ago, bom=bom)
        production.button_mark_done()
        self._assert_dates(production, self.month_ago)
        self.assertEqual(self.byproduct.qty_available, 1)

    def test_finished_serial_number(self):
        self.finished.tracking = "serial"
        production = self._production(self.month_ago)
        lot = self.env["stock.production.lot"].create({
            "name": "BACKDATE-SERIAL-001", "product_id": self.finished.id,
            "company_id": production.company_id.id,
        })
        production.lot_producing_id = lot
        production.button_mark_done()
        self._assert_dates(production, self.month_ago)
        self.assertEqual(production.move_finished_ids.move_line_ids.lot_id, lot)

    def test_closed_period_rejects_posting(self):
        production = self._production(self.year_ago)
        self.env.company.period_lock_date = fields.Date.today() - timedelta(days=1)
        with self.assertRaisesRegex(UserError, "accounting period is locked"), self.cr.savepoint():
            production.button_mark_done()
        self.assertNotEqual(production.state, "done")
        self.assertFalse(production.move_raw_ids.stock_valuation_layer_ids)
        self.assertEqual(self.component.qty_available, 100)

    def test_closed_fiscal_year_rejects_posting(self):
        production = self._production(self.year_ago)
        self.env.company.fiscalyear_lock_date = fields.Date.today() - timedelta(days=1)
        with self.assertRaisesRegex(UserError, "accounting period is locked"), self.cr.savepoint():
            production.button_mark_done()
        self.assertFalse(production.move_raw_ids.stock_valuation_layer_ids)

    def test_manual_valuation(self):
        self.category.property_valuation = "manual_periodic"
        production = self._production(self.year_ago)
        production.button_mark_done()
        self._assert_dates(production, self.year_ago)
        self.assertFalse(production.move_raw_ids.stock_valuation_layer_ids.account_move_id)

    def test_fifo_and_average(self):
        for cost_method in ("fifo", "average"):
            with self.subTest(cost_method=cost_method), self.cr.savepoint():
                self.category.property_cost_method = cost_method
                production = self._production(self.month_ago)
                production.button_mark_done()
                self._assert_dates(production, self.month_ago)

    def test_analytic_consumption_date(self):
        production = self._production(self.year_ago)
        production.analytic_account_id = self.env["account.analytic.account"].create({
            "name": "Backdate analytic", "company_id": production.company_id.id,
        })
        production.button_mark_done()
        lines = production.move_raw_ids.analytic_account_line_id
        self.assertTrue(lines)
        expected = fields.Datetime.context_timestamp(production, self.year_ago).date()
        self.assertEqual(set(lines.mapped("date")), {expected})

    def test_unrelated_transfer_and_later_revaluation_keep_current_date(self):
        production = self._production(self.year_ago)
        production.button_mark_done()
        receipt = self.env["stock.move"].create({
            "name": "Unrelated receipt", "product_id": self.component.id,
            "product_uom": self.uom.id, "product_uom_qty": 1,
            "location_id": self.supplier.id, "location_dest_id": self.stock.id,
        })
        receipt._action_confirm()
        receipt.quantity_done = 1
        started = fields.Datetime.now()
        receipt._action_done()
        self.assertGreaterEqual(receipt.date, started)
        self.assertFalse(receipt.stock_valuation_layer_ids.mrp_recorded_at)
        correction = self.env["stock.valuation.layer"].create({
            "product_id": self.finished.id, "company_id": self.env.company.id,
            "stock_move_id": production.move_finished_ids.id,
            "quantity": 0, "value": 1,
        })
        self.assertGreater(correction.create_date, self.month_ago)
        self.assertFalse(correction.mrp_recorded_at)
