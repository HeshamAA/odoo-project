from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tools import float_repr


class PurchaseOrderDiscount(models.TransientModel):
    _name = 'purchase.order.discount'
    _description = "Purchase Discount Wizard"

    purchase_order_id = fields.Many2one(
        'purchase.order',
        default=lambda self: self.env.context.get('active_id'),
        required=True,
    )
    company_id = fields.Many2one(related='purchase_order_id.company_id')
    currency_id = fields.Many2one(related='purchase_order_id.currency_id')
    discount_amount = fields.Monetary(string="Amount")
    discount_percentage = fields.Float(string="Percentage")
    discount_type = fields.Selection(
        selection=[
            ('pol_discount', "On All Order Lines"),
            ('po_discount', "Global Discount"),
            ('amount', "Fixed Amount"),
        ],
        default='pol_discount',
    )
 
    @api.model
    def default_get(self, fields_list):
      res = super().default_get(fields_list)

      purchase_order_id = self.env.context.get('active_id')
      if purchase_order_id:
        order = self.env['purchase.order'].browse(purchase_order_id)

        lines = order.order_line.filtered(
            lambda l: l.discount_ids and not l.display_type
        )

        if lines:
            lines.write({
        'discount': 0.0,
        'my_discount': 0.0,
    })

        return res
    @api.constrains('discount_type', 'discount_percentage')
    def _check_discount_amount(self):
        for wizard in self:
            if (
                wizard.discount_type in ('pol_discount', 'po_discount')
                and wizard.discount_percentage > 1.0
            ):
                raise ValidationError(_("Invalid discount amount"))

    def _prepare_discount_product_values(self):
        self.ensure_one()
        values = {
            'name': _('Discount'),
            'type': 'service',
            'purchase_ok': True,
            'list_price': 0.0,
            'company_id': self.company_id.id,
            'supplier_taxes_id': None,
        }
        services_category = self.env.ref('product.product_category_services', raise_if_not_found=False)
        if services_category:
            values['categ_id'] = services_category.id
        return values

    def _get_discount_product(self):
        self.ensure_one()
        company = self.company_id
        discount_product = company.purchase_discount_product_id
        if not discount_product:
            if (
                self.env['product.product'].has_access('create')
                and company.has_access('write')
            ):
                company.purchase_discount_product_id = self.env['product.product'].create(
                    self._prepare_discount_product_values()
                )
            else:
                raise ValidationError(_(
                    "There does not seem to be any discount product configured for this company yet."
                    " Ask an administrator to apply the discount the first time."
                ))
            discount_product = company.purchase_discount_product_id
        return discount_product

    def _prepare_global_discount_po_lines(self, base_lines):
        self.ensure_one()
        discount_dp = self.env['decimal.precision'].precision_get('Discount')
        has_multiple_tax_combinations = len(
            set(base_line['tax_ids'] for base_line in base_lines if base_line['tax_ids'])
        ) > 1
        po_line_values_list = []
        for base_line in base_lines:
            if has_multiple_tax_combinations:
                if self.discount_type == 'po_discount':
                    description = self.env._(
                        "Discount %(percent)s%%"
                        " - On products with the following taxes %(taxes)s",
                        percent=float_repr(self.discount_percentage * 100.0, discount_dp),
                        taxes=", ".join(base_line['tax_ids'].mapped('name')),
                    )
                else:
                    description = self.env._(
                        "Discount"
                        " - On products with the following taxes %(taxes)s",
                        taxes=", ".join(base_line['tax_ids'].mapped('name')),
                    )
            else:
                if self.discount_type == 'po_discount':
                    description = self.env._(
                        "Discount %(percent)s%%",
                        percent=float_repr(self.discount_percentage * 100.0, discount_dp),
                    )
                else:
                    description = self.env._("Discount")

            # price_unit holds the actual computed discount amount (negative) for correct accounting.
            # price_unit_before_discount is used for display only: show the absolute discount value.
            actual_price_unit = base_line['price_unit']
            display_price_unit = actual_price_unit * base_line['quantity']

            po_line_values_list.append({
                'name': description,
                'product_id': base_line['product_id'].id,
                'price_unit': actual_price_unit,
                'price_unit_before_discount': display_price_unit,
                'product_qty': base_line['quantity'],
                'tax_ids': [Command.set(base_line['tax_ids'].ids)],
                'date_planned': fields.Datetime.now(),
                'sequence': 999,
            })
        return po_line_values_list

    def _create_discount_lines(self):
        self.ensure_one()
        self = self.with_context(lang=self.purchase_order_id.partner_id.lang)

        discount_product = self._get_discount_product()

        if self.discount_type == 'po_discount':
            amount_type = 'percent'
            amount = self.discount_percentage * 100.0
        else:  # amount
            amount_type = 'fixed'
            amount = self.discount_amount

        order = self.purchase_order_id
        AccountTax = self.env['account.tax']
        order_lines = order.order_line.filtered(lambda x: not x.display_type)
        base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
        AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
        AccountTax._round_base_lines_tax_details(base_lines, order.company_id)

        def grouping_function(base_line):
            return {'product_id': discount_product}

        global_discount_base_lines = AccountTax._prepare_global_discount_lines(
            base_lines=base_lines,
            company=self.company_id,
            amount_type=amount_type,
            amount=amount,
            computation_key=f'purchase_global_discount,{self.id}',
            grouping_function=grouping_function,
        )
        order.order_line = [
            Command.create(values)
            for values in self._prepare_global_discount_po_lines(global_discount_base_lines)
        ]

    def action_apply_discount(self):
             self.ensure_one()
             self = self.with_company(self.company_id)

             if self.discount_type == 'pol_discount':
               percentage = self.discount_percentage * 100

               lines = self.purchase_order_id.order_line.filtered(
                   lambda l: not l.display_type
               )
     
               for line in lines:
                  
                 if line.discount_ids:
                    continue

                 line.write({
                'my_discount': percentage,
                'discount': 0.0,
             })
                 line._compute_price_unit_and_date_planned_and_name()
             else:
                self._create_discount_lines()