from collections import defaultdict

from odoo import api, fields, models


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    mrp_recorded_at = fields.Datetime(
        string="Actually Recorded On",
        readonly=True,
        copy=False,
        help="Original creation timestamp of a backdated manufacturing valuation.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        layers = super().create(vals_list)
        grouped = defaultdict(lambda: self.env["stock.valuation.layer"])
        for layer in layers:
            # Zero-quantity revaluations (including FIFO vacuum corrections)
            # belong to their own posting date, not the original production.
            if not layer.stock_move_id or not layer.quantity:
                continue
            backdate = layer.stock_move_id._get_mrp_stock_backdate()
            if backdate:
                layer.mrp_recorded_at = layer.create_date
                grouped[backdate] |= layer
        for backdate, backdated_layers in grouped.items():
            # Odoo 15's valuation-at-date report filters create_date. Its ORM
            # protects this audit column, so update ONLY the freshly created
            # layers and preserve the real timestamp in mrp_recorded_at.
            backdated_layers.flush(["create_date", "mrp_recorded_at"])
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET create_date = %s WHERE id IN %s",
                [backdate, tuple(backdated_layers.ids)],
            )
            backdated_layers.invalidate_cache(["create_date"])
        return layers
