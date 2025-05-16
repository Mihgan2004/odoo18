# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cdek_pvz_id = fields.Many2one(
        'cdek.pvz',
        string='ПВЗ СДЭК',
        tracking=True,
        domain="[('city_name', '=ilike', partner_shipping_id_city), ('country_code', '=ilike', partner_shipping_id_country_code)]"
    )

    partner_shipping_id_city = fields.Char(
        related='partner_shipping_id.city',
        string="Город получателя (СДЭК)",
        store=True,
        readonly=True
    )
    partner_shipping_id_country_code = fields.Char(
        related='partner_shipping_id.country_id.code',
        string="Код страны получателя (СДЭК)",
        store=True,
        readonly=True
    )
    cdek_pvz_code = fields.Char(
        related='cdek_pvz_id.code',
        string='Код ПВЗ',
        store=True,
        readonly=True
    )
    cdek_pvz_name_display = fields.Char( 
        related='cdek_pvz_id.name',
        string='Наименование ПВЗ',
        store=True,
        readonly=True
    )
    cdek_pvz_address_full = fields.Text(
        related='cdek_pvz_id.address_full',
        string='Адрес ПВЗ',
        store=True,
        readonly=True
    )

    cdek_order_uuid = fields.Char(
        string="CDEK Order UUID",
        readonly=True,
        copy=False,
        help="Идентификатор заказа, возвращаемый /v2/orders."
    )

    def action_view_cdek_tracking(self):
            """
            Открывает страницу трекинга CDEK в новой вкладке браузера.
            """
            self.ensure_one()
            if not self.cdek_order_uuid:
                raise UserError(_("CDEK order UUID is not set."))

            track_url = f"https://www.cdek.ru/tracking?tracking_id={self.cdek_order_uuid}"

            return {
                "type": "ir.actions.act_url",
                "url": track_url,
                "target": "new",
            }

    # cdek_pvz_id = fields.Char(...) - удалить, если это старое Char поле
    # cdek_pvz_address = fields.Char(...) - удалить
    # cdek_pvz_name = fields.Char(...) - удалить

    # _compute_cdek_pvz_details - больше не нужен, данные берутся через related поля
    # def _compute_cdek_pvz_details(self):
    #     for order in self:
    #         if order.cdek_pvz_id: # Это уже Many2one
    #             order.cdek_pvz_code = order.cdek_pvz_id.code
    #             order.cdek_pvz_name_display = order.cdek_pvz_id.name # или как вы назвали поле
    #             order.cdek_pvz_address_full = order.cdek_pvz_id.address_full
    #         else:
    #             order.cdek_pvz_code = False
    #             order.cdek_pvz_name_display = False
    #             order.cdek_pvz_address_full = False


    @api.onchange('cdek_pvz_id')
    def _onchange_cdek_pvz_id_new(self):
        if self.cdek_pvz_id:
            # ...
            if hasattr(self, 'get_delivery_price'): 
                self.get_delivery_price()
        else:
            pass


    @api.model
    def get_cdek_api_config(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'cdek_client_id': params.get_param('cdek.api.client_id', False),
            'cdek_client_secret': params.get_param('cdek.api.client_secret', False),
            'yandex_maps_api_key': params.get_param('yandex.maps.api.key', False),
            'cdek_api_url': params.get_param('cdek.api.url', 'https://api.cdek.ru/v2'),
            'cdek_token_url': params.get_param('cdek.token.url', 'https://api.cdek.ru/v2/oauth/token?parameters'),
        }