from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    discount_ids = fields.Many2many(
        'purchase.discount',
        'purchase_order_line_discount_rel',
        'line_id',
        'discount_id',
        string='Discounts',
        context={'active_test': True},
    )

    price_unit_before_discount = fields.Float(
        string='Unit Price',
        digits='Product Price',
        store=True,
        copy=True,
        default=0.0,
    )

    price_unit = fields.Float(
        string='Unit Price',
        digits='Product Price',
        compute='_compute_price_unit_and_date_planned_and_name',
        store=True,
        readonly=False,
    )
    my_discount = fields.Float(
    string="Discount %",
    digits='Discount',
    default=0.0,
)

    @api.constrains('discount_ids', 'my_discount')
    def _check_discount_exclusivity(self):
      for line in self:
        if line.discount_ids and line.my_discount:
            raise ValidationError(
                _("You cannot use a normal discount with multiple discounts.")
            )

              
    @api.onchange('discount_ids', 'my_discount')
    def _onchange_discount_ids(self):
     for line in self:
        if line.discount_ids:
            line.my_discount = 0.0  


    @api.depends(
      'price_unit_before_discount',
    'discount_ids.discount_value',
    'my_discount',
    'product_qty',
    'product_id',
    'currency_id',
)
    def _compute_price_unit_and_date_planned_and_name(self):

      super()._compute_price_unit_and_date_planned_and_name()

      for line in self:

        if not line.product_id:
            continue

        discount_product = line.company_id.purchase_discount_product_id
        if discount_product and line.product_id == discount_product:
            continue

        if not line.price_unit_before_discount:
             line.price_unit_before_discount = line.price_unit

        base = line.price_unit_before_discount

        if not base:
            base = line.price_unit

        if not base:
            continue


        # ===============================
        # Discount calculation
        # ===============================

        if line.discount_ids:
            price = base

            for discount in line.discount_ids:
                  price *= (
                     1.0 - discount.discount_value / 100.0
                   )

            line.price_unit = max(price, 0.0)

        elif line.my_discount:
            line.price_unit = base * (
              1.0 - line.my_discount / 100.0
            )

        else:
            line.price_unit = base
    @api.onchange('price_unit_before_discount')
    def _onchange_price_unit_before_discount(self):
        for line in self:
            if not line.discount_ids:
                line.price_unit = line.price_unit_before_discount

    

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        print(
        "PREPARE BILL:",
        self.product_id.name,
        "PRICE:",
        self.price_unit,
        "DISCOUNT:",
        self.discount,
        "DISCOUNT IDS:",
        self.discount_ids.ids,
        )
        baked =  self.discount_ids  or self.my_discount 

        if baked:
            res['discount'] = 0.0
            res['price_unit'] = self.price_unit
            aml_currency = move and move.currency_id or self.currency_id
            date = move and move.date or fields.Date.today()
            price_unit_converted = self.currency_id._convert(
                self.price_unit, aml_currency, self.company_id, date, round=False
            )
            qty = -self.qty_to_invoice if move and move.move_type == 'in_refund' else self.qty_to_invoice
            total_wo_tax = self.tax_ids.with_context(round=False, round_base=False).compute_all(
                price_unit_converted,
                currency=aml_currency,
                quantity=qty,
                product=self.product_id,
            )['total_excluded']
            res['balance'] = self.currency_id._convert(
                total_wo_tax,
                self.company_id.currency_id,
                round=False,
            )
        return res

    @api.model_create_multi
    def create(self, vals_list):
     for vals in vals_list:
        if vals.get('discount_ids') and vals.get('discount'):
            vals['discount'] = 0.0

     return super().create(vals_list)


    def write(self, vals):
     if 'discount_ids' in vals:
        discount_commands = vals['discount_ids']

        # لو فيه إضافة discounts
        has_discount_ids = bool(discount_commands)
     else:
        has_discount_ids = bool(self.discount_ids)

     if has_discount_ids:
        vals['discount'] = 0.0
        vals['my_discount'] = 0.0

     return super().write(vals)