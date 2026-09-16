from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_backdate_production(self):
        self.ensure_one()
        if self.scrapped or self.origin_returned_move_id or self.unbuild_id:
            return self.env["mrp.production"]
        return self.raw_material_production_id or self.production_id

    def _get_mrp_stock_backdate(self):
        """Only expose the date during this batch's initial stock posting."""
        production = self._get_backdate_production()
        dates = self.env.context.get("mrp_stock_backdate_dates", {})
        value = dates.get(production.id) if production else False
        return fields.Datetime.to_datetime(value) if value else False

    def _get_mrp_accounting_date(self):
        backdate = self._get_mrp_stock_backdate()
        if backdate:
            # Inventory datetimes are UTC; accounting uses the user's local day.
            return fields.Datetime.context_timestamp(self, backdate).date()
        return False

    def _check_mrp_backdate_lock(self, backdate):
        self.ensure_one()
        product = self.product_id.with_company(self.company_id)
        if product.type != "product" or product.valuation != "real_time":
            return
        accounting_date = fields.Datetime.context_timestamp(self, backdate).date()
        lock_dates = [date for date in (
            self.company_id.fiscalyear_lock_date,
            self.company_id.period_lock_date,
        ) if date]
        if lock_dates and accounting_date <= max(lock_dates):
            raise UserError(_(
                "Cannot validate manufacturing order %(order)s with inventory "
                "date %(date)s: the accounting period is locked through %(lock)s. "
                "Review the scheduled date or the company's lock dates."
            ) % {
                "order": self._get_backdate_production().display_name,
                "date": accounting_date,
                "lock": max(lock_dates),
            })

    def _action_done(self, cancel_backorder=False):
        dates = {}
        for move in self.filtered(lambda item: item.state not in ("done", "cancel")):
            production = move._get_backdate_production()
            backdate = production._get_stock_backdate() if production else False
            if backdate:
                move._check_mrp_backdate_lock(backdate)
                dates[production.id] = fields.Datetime.to_string(backdate)

        # A per-production mapping keeps mixed batches and additional/split
        # moves independent, without imposing an MRP date on chained transfers.
        moves = self.with_context(mrp_stock_backdate_dates=dates)
        done_moves = super(StockMove, moves)._action_done(
            cancel_backorder=cancel_backorder,
        )
        grouped = defaultdict(lambda: self.env["stock.move"])
        for move in done_moves:
            backdate = move._get_mrp_stock_backdate()
            if backdate and move.state == "done":
                grouped[backdate] |= move
        for backdate, posted_moves in grouped.items():
            posted_moves.write({"date": backdate})
            posted_moves.move_line_ids.write({"date": backdate})
        # Do not leak this posting's dates into later valuation corrections.
        return done_moves.with_env(self.env)

    def _prepare_account_move_vals(
        self, credit_account_id, debit_account_id, journal_id,
        qty, description, svl_id, cost,
    ):
        vals = super()._prepare_account_move_vals(
            credit_account_id, debit_account_id, journal_id,
            qty, description, svl_id, cost,
        )
        accounting_date = self._get_mrp_accounting_date()
        if accounting_date and self.env["stock.valuation.layer"].browse(svl_id).quantity:
            vals["date"] = accounting_date
        return vals

    def _generate_analytic_lines_data(self, unit_amount, amount):
        vals = super()._generate_analytic_lines_data(unit_amount, amount)
        accounting_date = self._get_mrp_accounting_date()
        if accounting_date:
            vals["date"] = accounting_date
        return vals
