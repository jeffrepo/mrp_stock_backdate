from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _get_stock_backdate(self):
        """Use the scheduled date only for a production in the past."""
        self.ensure_one()
        if self.date_planned_start and self.date_planned_start < fields.Datetime.now():
            return self.date_planned_start
        return False

    def _get_backorder_mo_vals(self):
        vals = super()._get_backorder_mo_vals()
        if self._get_stock_backdate():
            # Odoo's schedule fields have copy=False. A partial production must
            # not silently replace the original effective date with today.
            vals.update({
                "date_planned_start": self.date_planned_start,
                "date_planned_finished": self.date_planned_finished,
            })
        return vals
