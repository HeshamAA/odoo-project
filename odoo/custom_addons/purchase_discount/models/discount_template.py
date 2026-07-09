from odoo import fields, models,api


class PurchaseDiscount(models.Model):
    _name = 'purchase.discount'
    _description = 'Purchase Discount'
    _order = 'name'

    name = fields.Char(required=True)
    discount_value = fields.Float('Percentage (%)', required=True, digits='Discount')

    @api.depends('name', 'discount_value')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"{rec.name} ({rec.discount_value}%)"
            )