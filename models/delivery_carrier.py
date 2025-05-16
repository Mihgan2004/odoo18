# -*- coding: utf-8 -*-
import base64
import re
import logging
from unidecode import unidecode
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date # Добавлен date
from ..const import CDEK_ORDER_TYPE_IM, CDEK_LABEL_FORMATS, DEFAULT_LENGTH_CM, DEFAULT_WIDTH_CM, DEFAULT_HEIGHT_CM, DEFAULT_WEIGHT_KG

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("cdek", "CDEK")],
        ondelete={"cdek": "set default"},
    )

    cdek_tariff_code = fields.Integer(
        string='CDEK Tariff Code',
        help="Numeric CDEK tariff code (e.g., 136). Required for CDEK carriers."
    )
    cdek_shipment_point_code = fields.Char(
        string="CDEK Shipment Point (PVZ Code)",
        help="PVZ Code for self-delivery to CDEK if tariff requires shipment from CDEK warehouse. "
             "This PVZ code will be used in 'shipment_point' field in CDEK API /orders request. "
             "Cannot be used simultaneously with 'from_location' (sender's address)."
    )
    cdek_order_type = fields.Selection([
        ('1', 'Интернет-магазин'),
        ('2', 'Доставка (обычная)')
        ], string="CDEK Order Type", default='1', required=True,
        help="1 - 'Интернет-магазин' (только для договора типа 'Договор с ИМ'), "
             "2 - 'Доставка' (для любого договора).")


    cdek_label_format_override = fields.Selection(
        CDEK_LABEL_FORMATS,
        string='Label Format (Override)',
        help="Override the global default label format for this CDEK carrier."
    )
    cdek_add_days = fields.Integer(
        string='Additional Processing Days', # Переименовано для ясности
        default=0,
        help='Add this many days to the CDEK delivery estimate for internal processing.'
    )
    cdek_allow_cod = fields.Boolean(
        string="Allow Cash on Delivery (COD)",
        default=False,
        help="If checked, Cash on Delivery will be enabled for shipments using this method. "
             "Ensure 'payment' field is correctly set for items in packages."
    )
    

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='company_id.currency_id', store=True, readonly=True,
        help="Currency for pricing rules and thresholds."
    )

    
    cdek_free_shipping_threshold = fields.Monetary(
        string="CDEK Free Shipping Threshold",
        currency_field="currency_id", # <--- ИСПРАВЛЕНИЕ ОШИБКИ
        help="If order total (untaxed) is above this amount, CDEK shipping via this method is free."
    )



    @api.constrains('delivery_type', 'cdek_tariff_code', 'cdek_order_type')
    def _check_cdek_settings(self):
        for record in self:
            if record.delivery_type == 'cdek':
                if not record.cdek_tariff_code:
                    raise ValidationError(_("CDEK Tariff Code is required for CDEK delivery methods."))
                if not record.cdek_order_type:
                    raise ValidationError(_("CDEK Order Type is required for CDEK delivery methods."))
                if record.cdek_shipment_point_code and not record.cdek_shipment_point_code.isdigit():
                    raise ValidationError(_("CDEK Shipment Point Code must be a numeric code if provided."))


    def _get_cdek_client(self):
        self.ensure_one()

        client = self.env['res.config.settings']._get_cdek_client(carrier=self)
        if not client:
             raise UserError(_("CDEK client could not be initialized. Please configure CDEK API credentials in settings."))
        return client

    def _cdek_get_label_format(self):
        self.ensure_one()
        if self.cdek_label_format_override:
            return self.cdek_label_format_override
        return self.env['ir.config_parameter'].sudo().get_param('cdek.default_label_format', 'pdf')

    def _cdek_prepare_contact_info(self, partner, is_sender=False):
        if not partner:
            error_msg = _("Sender partner is missing.") if is_sender else _("Recipient partner is missing.")
            raise UserError(error_msg)

        name_str = partner.name
        company_name_str = None

        if partner.is_company and not partner.parent_id:
            company_name_str = partner.name
        elif partner.parent_id and partner.parent_id.is_company:
            company_name_str = partner.parent_id.name
            name_str = partner.name
        
        if not name_str:
            error_msg = _("Contact name for CDEK %s is missing.") % ("sender" if is_sender else "recipient")
            raise UserError(error_msg)

        contact_data = {'name': name_str[:100]}
        if company_name_str:
             contact_data['company'] = company_name_str[:100]

        phones_payload = []
        phone_number = partner.mobile or partner.phone
        if phone_number:
            cleaned_phone = re.sub(r'\D', '', phone_number)
            if cleaned_phone:
                phones_payload.append({'number': cleaned_phone})
        
        if not phones_payload: 
             error_msg = _("Phone number is required by CDEK for %s (%s).") % (("sender" if is_sender else "recipient"), name_str)
             raise UserError(error_msg)
        contact_data['phones'] = phones_payload

        if partner.email:
            contact_data['email'] = partner.email
        return contact_data

    def _cdek_prepare_location_info(self, partner, is_pvz_delivery_point=False, pvz_code=None, is_sender_shipment_point=False, sender_pvz_code=None):
        if is_pvz_delivery_point:
            if not pvz_code: raise UserError(_("PVZ code for recipient (delivery_point) is required."))
            return {'code': int(pvz_code)}
        if is_sender_shipment_point:
            if not sender_pvz_code: raise UserError(_("PVZ code for sender (shipment_point) is required."))
            return {'code': int(sender_pvz_code)}

        if not partner: raise UserError(_("Partner for address location is missing."))

        if not partner.city or not partner.street or not partner.country_id or not partner.country_id.code:
            missing = [fN for fN, fV in [('City', partner.city), ('Street', partner.street), ('Country', partner.country_id)] if not fV]
            raise UserError(_("Address for %s is incomplete. Missing: %s") % (partner.name, ", ".join(missing)))

        full_address = partner.street
        if partner.street2: full_address += f", {partner.street2}"

        location_data = {
            'country_code': partner.country_id.code,
            'city': partner.city,
            'address': full_address,
        }
        if partner.zip: location_data['postal_code'] = partner.zip
        
        return location_data

    def _cdek_prepare_packages_payload(self, picking_or_order, order_for_cod_ref=None):
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        packages_payload = []
        
        is_order = picking_or_order._name == 'sale.order'
        record = picking_or_order
        
        # Используем переданный order_for_cod_ref или получаем его
        actual_order_for_cod = order_for_cod_ref if order_for_cod_ref else (record if is_order else record.sale_id)

        default_length = int(round(float(params.get_param('cdek.default_length_cm', DEFAULT_LENGTH_CM))))
        default_width  = int(round(float(params.get_param('cdek.default_width_cm', DEFAULT_WIDTH_CM))))
        default_height = int(round(float(params.get_param('cdek.default_height_cm', DEFAULT_HEIGHT_CM))))
        default_weight_one_item_kg = float(params.get_param('cdek.default_weight_kg', DEFAULT_WEIGHT_KG))

        items_for_package = []
        total_package_weight_grams = 0

        lines_to_process = record.order_line.filtered(lambda l: not l.display_type and l.product_id.type in ['product', 'consu']) if is_order \
            else record.move_line_ids.filtered(lambda ml: ml.product_id.type in ['product', 'consu'] and (ml.qty_done > 0 or ml.product_uom_qty > 0))

        if not lines_to_process:
            _logger.warning("CDEK: No product lines in %s %s. Using default item.", record._name, record.name)
            item_weight_g = max(10, int(round(default_weight_one_item_kg * 1000)))
            items_for_package.append({
                "name": _("Default Goods"), "ware_key": "DEFAULT_ITEM_SKU", "cost": 0.01, # Минимальная стоимость
                "weight": item_weight_g, "amount": 1,
            })
            total_package_weight_grams = item_weight_g
        else:
            for line in lines_to_process:
                product = line.product_id
                qty = int(line.product_uom_qty if is_order else (line.qty_done or line.product_uom_qty))
                if qty <= 0: continue

                item_weight_grams = max(10, int(round((product.weight or default_weight_one_item_kg) * 1000)))
                total_package_weight_grams += item_weight_grams * qty
                
                cost_per_unit = 0.01 
                if is_order:
                    cost_per_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                elif actual_order_for_cod: # picking
                    so_line = actual_order_for_cod.order_line.filtered(lambda sol: sol.product_id == product)[:1]
                    if so_line: cost_per_unit = so_line.price_unit * (1-(so_line.discount or 0.0)/100.0)
                    else: cost_per_unit = product.list_price
                cost_per_unit = max(0.01, round(cost_per_unit, 2))


                item_payload = {
                    "name": product.name[:255],
                    "ware_key": product.default_code or f"SKU_{product.id}",
                    "cost": cost_per_unit,
                    "weight": item_weight_grams,
                    "amount": qty,
                    # "vat_rate": product.supplier_taxes_id[:1].amount_type == 'percent' and int(product.supplier_taxes_id[:1].amount) or 0 # Пример НДС
                }
                if self.cdek_allow_cod and actual_order_for_cod:
                    payment_value_for_item = cost_per_unit
                    item_payload["payment"] = {"value": payment_value_for_item}
                items_for_package.append(item_payload)

        if not items_for_package: raise UserError(_("CDEK: No items for package in %s %s.") % (record._name, record.name))
        if total_package_weight_grams <= 0: total_package_weight_grams = 10 # Минимальный вес

        packages_payload.append({
            "number": "1", "weight": total_package_weight_grams,
            "length": default_length, "width": default_width, "height": default_height,
            "items": items_for_package,
        })
        return packages_payload

    # --- Методы API Odoo для способов доставки ---
    def cdek_rate_shipment(self, order):
        self.ensure_one()
        _logger.info("CDEK rating for SaleOrder %s via carrier %s", order.name, self.name)
        client = self._get_cdek_client()
        if self.cdek_free_shipping_threshold > 0 and order.amount_untaxed >= self.cdek_free_shipping_threshold:
            return {'success': True, 'price': 0.0, 'error_message': False, 'warning_message': _("Free shipping by CDEK threshold")}


        sender_partner = order.warehouse_id.partner_id or self.env.company.partner_id
        from_location_payload = {}
        if self.cdek_shipment_point_code : 
             from_location_payload = {'code': int(self.cdek_shipment_point_code)} 
        else: 
            try: from_location_payload = self._cdek_prepare_location_info(sender_partner)
            except UserError as e: return self._rate_error(str(e))


        recipient_partner = order.partner_shipping_id
        to_location_payload = {}
        if order.cdek_pvz_id and order.cdek_pvz_id.code: 
            to_location_payload = self._cdek_prepare_location_info(None, is_pvz_delivery_point=True, pvz_code=order.cdek_pvz_id.code)
        else:
            try: to_location_payload = self._cdek_prepare_location_info(recipient_partner)
            except UserError as e: return self._rate_error(str(e))

        try: packages_payload = self._cdek_prepare_packages_payload(order)
        except UserError as e: return self._rate_error(str(e))

        currency_code = order.currency_id.name if order.currency_id else 'RUB'


        calc_payload = {
            'type': int(self.cdek_order_type),
            'tariff_code': self.cdek_tariff_code,
            'from_location': from_location_payload, # Будет использоваться, если cdek_shipment_point_code не задан
            'to_location': to_location_payload,     # Будет использоваться, если cdek_pvz_id не задан
            'packages': packages_payload,
        }

        if self.cdek_shipment_point_code:
             pvz_sender = self.env['cdek.pvz'].sudo().search([('code', '=', self.cdek_shipment_point_code)], limit=1)
             if pvz_sender: calc_payload['from_location'] = self._cdek_prepare_location_info(pvz_sender, is_sender=True) # Используем адрес ПВЗ как адрес
             else: return self._rate_error(_("Sender PVZ with code %s not found.") % self.cdek_shipment_point_code)
        
        if order.cdek_pvz_id:
             calc_payload['to_location'] = self._cdek_prepare_location_info(order.cdek_pvz_id) # Используем адрес ПВЗ как адрес


        try:
            # calc_payload_for_list не должен содержать tariff_code
            # tarifflist_payload = calc_payload.copy()
            # tarifflist_payload.pop('tariff_code', None)
            # available_tariffs = client.calculate_tariff_list(tarifflist_payload)
            # self.env['cdek.tariff']._process_api_tariffs(available_tariffs) 
            
            _logger.info("CDEK Rating Request: %s", calc_payload)
            result = client.calculate_tariff(calc_payload)
            _logger.info("CDEK Rating Response: %s", result)
            if not result or 'total_sum' not in result:
                error_msg_parts = []
                if result and result.get('errors'):
                    for err_item in result['errors']: # API может вернуть список ошибок
                        error_msg_parts.append(f"Code: {err_item.get('code')}, Message: {err_item.get('message')}")
                error_msg = _("CDEK Rate: Failed to get a valid rate. Details: %s") % ("; ".join(error_msg_parts) or str(result))
                return self._rate_error(error_msg)

            price = float(result['total_sum'])
            delivery_period_min = result.get('period_min', 0)
            delivery_period_max = result.get('period_max', 0)
            delivery_time_str = ""
            # ... (логика формирования delivery_time_str) ...
            if delivery_period_min == delivery_period_max and delivery_period_min > 0:
                 delivery_time_str = _("%s days") % delivery_period_min
            elif delivery_period_min > 0 and delivery_period_max > 0:
                 delivery_time_str = _("%s-%s days") % (delivery_period_min, delivery_period_max)
            if self.cdek_add_days > 0:
                 add_days_str = _(" (+%s processing days)") % self.cdek_add_days
                 delivery_time_str = (delivery_time_str + add_days_str) if delivery_time_str else add_days_str.strip()[1:-1]


            return {'success': True, 'price': price, 'error_message': False, 
                    'warning_message': result.get('warnings') or False, 'delivery_time': delivery_time_str or False}
        except UserError as e: return self._rate_error(str(e))
        except Exception as e:
            _logger.exception("CDEK Rating General Exception:")
            return self._rate_error(_("Unexpected error during CDEK rating: %s") % str(e))

    def _build_order_payload(self, picking): 
        self.ensure_one()
        sale_order = picking.sale_id
        if not sale_order:
            raise UserError(_("Picking %s is not linked to a Sale Order. CDEK shipment cannot be created.") % picking.name)

        sender_partner = picking.picking_type_id.warehouse_id.partner_id or self.env.company.partner_id
        recipient_partner = picking.partner_id

        sender_contact_payload = self._cdek_prepare_contact_info(sender_partner, is_sender=True, for_order_api=True)
        recipient_contact_payload = self._cdek_prepare_contact_info(recipient_partner, for_order_api=True)

        from_location_payload, shipment_point_code_str = (None, None)
        if self.cdek_shipment_point_code:
            shipment_point_code_str = self.cdek_shipment_point_code
        else:
            from_location_payload = self._cdek_prepare_location_info(sender_partner, is_sender=True)

        to_location_payload, delivery_point_code_str = (None, None)
        if sale_order.cdek_pvz_id and sale_order.cdek_pvz_id.code:
            delivery_point_code_str = sale_order.cdek_pvz_id.code
        else:
            to_location_payload = self._cdek_prepare_location_info(recipient_partner)

        packages_payload, _ = self._cdek_prepare_packages_payload(picking, order_for_cod_ref=sale_order)

        payload = {
            'type': int(self.cdek_order_type),
            'number': picking.name[:50],
            'tariff_code': self.cdek_tariff_code,
            'comment': (sale_order.note or picking.note or "")[:255],
            'recipient': recipient_contact_payload,
            'packages': packages_payload,
        }

        if shipment_point_code_str: payload['shipment_point'] = shipment_point_code_str
        elif from_location_payload: payload['from_location'] = from_location_payload
        else: raise UserError(_("Sender location (PVZ or Address) is not defined for CDEK order."))

        if delivery_point_code_str: payload['delivery_point'] = delivery_point_code_str
        elif to_location_payload: payload['to_location'] = to_location_payload
        else: raise UserError(_("Recipient location (PVZ or Address) is not defined for CDEK order."))

        if int(self.cdek_order_type) == 2 or not self.env['ir.config_parameter'].sudo().get_param('cdek.sender_is_defaulted_by_contract'):
            payload['sender'] = sender_contact_payload
            
        company = picking.company_id or self.env.company
        if company:
             seller_address_parts = filter(None, [company.partner_id.street, company.partner_id.street2, company.partner_id.city])
             seller_payload = {
                 "name": company.name, "inn": company.vat,
                 "phone": re.sub(r'\D', '', company.phone or company.partner_id.phone or ''),
                 "address": ", ".join(seller_address_parts),
             }
             payload['seller'] = {k: v for k, v in seller_payload.items() if v}
        
        # if hasattr(self, 'cdek_delivery_recipient_cost') and self.cdek_delivery_recipient_cost > 0:
        #     payload['delivery_recipient_cost'] = {'value': self.cdek_delivery_recipient_cost}

        return payload

    def cdek_send_shipping(self, pickings):
        self.ensure_one()
        client = self._get_cdek_client()
        results = []

        for picking in pickings:
            if picking.carrier_tracking_ref and picking.cdek_order_uuid:
                _logger.info("CDEK: Picking %s already sent (UUID: %s)", picking.name, picking.cdek_order_uuid)
                results.append({'exact_price': picking.carrier_price or 0.0, 'tracking_number': picking.cdek_order_uuid})
                continue
            try:
                payload = self._build_order_payload(picking)
                _logger.info("CDEK Send Shipping Payload for %s: %s", picking.name, payload)
                response_data = client.create_order(payload)
                _logger.info("CDEK Send Shipping Response for %s: %s", picking.name, response_data)

                cdek_uuid = None
                if response_data and response_data.get('entity') and response_data['entity'].get('uuid'):
                    cdek_uuid = response_data['entity']['uuid']
                elif response_data and response_data.get('requests') and response_data['requests'][0].get('related_entities'):
                    for rentity in response_data['requests'][0]['related_entities']:
                        if rentity.get('type') == 'ORDER' and rentity.get('uuid'):
                            cdek_uuid = rentity['uuid']
                            break
                
                if not cdek_uuid:
                    error_msg_parts = []
                    api_requests_info = response_data.get('requests') if isinstance(response_data, dict) else None
                    if api_requests_info and isinstance(api_requests_info, list) and api_requests_info[0].get('errors'):
                        for err in api_requests_info[0]['errors']:
                            error_msg_parts.append(f"Code: {err.get('code')}, Message: {err.get('message')}")
                    final_error_msg = _("CDEK: Failed to register order %s. Details: %s") % (
                        picking.name, "; ".join(error_msg_parts) if error_msg_parts else str(response_data)
                    )
                    results.append({'error_message': final_error_msg, 'exact_price': 0.0})
                    picking.message_post(body=final_error_msg)
                    continue

                picking.write({
                    'carrier_tracking_ref': cdek_uuid,
                    'cdek_order_uuid': cdek_uuid,
                })
                if picking.sale_id: picking.sale_id.cdek_order_uuid = cdek_uuid

                results.append({'exact_price': picking.carrier_price or 0.0, 'tracking_number': cdek_uuid})
                picking.message_post(body=_("Successfully registered with CDEK. Order UUID: %s") % cdek_uuid)

            except UserError as e: # Ошибки UserError от _build_order_payload или CdekRequest
                error_msg = _("CDEK API Error for Picking %s: %s") % (picking.name, str(e))
                _logger.error(error_msg)
                results.append({'error_message': error_msg, 'exact_price': 0.0})
                picking.message_post(body=error_msg)
            except Exception as e:
                _logger.exception("CDEK Send Shipping General Exception for %s:", picking.name)
                error_msg = _("Unexpected error sending Picking %s to CDEK: %s") % (picking.name, str(e))
                results.append({'error_message': error_msg, 'exact_price': 0.0})
                picking.message_post(body=error_msg)
        return results



    @staticmethod
    def _rate_error(msg: str) -> dict:
        """Return structure compatible with delivery._get_rate() expectations."""
        return dict(success=False, price=0.0, error_message=msg, warning_message=False)
    
    def _cdek_prepare_location_info(
        self, partner=None, *,            
        is_sender=False, is_pvz_delivery_point=False,
        pvz_code=None, is_sender_shipment_point=False,
        sender_pvz_code=None
    ):
     
        if is_pvz_delivery_point:
            if not pvz_code:
                raise UserError(_("PVZ code for delivery_point is required"))
            return {'code': int(pvz_code)}

        if is_sender_shipment_point:
            if not sender_pvz_code:
                raise UserError(_("PVZ code for shipment_point is required"))
            return {'code': int(sender_pvz_code)}

        if not partner:
            raise UserError(_("Partner is missing for location_info"))

        missing = [n for n, v in [('City', partner.city),
                                  ('Street', partner.street),
                                  ('Country', partner.country_id and partner.country_id.code)] if not v]
        if missing:
            raise UserError(_("Address for %s is incomplete. Missing: %s") % (partner.name, ", ".join(missing)))
        full_address = partner.street
        if partner.street2:
            full_address += f", {partner.street2}"
        return {
            'country_code': partner.country_id.code,
            'city': partner.city,
            'address': full_address,
            'postal_code': partner.zip or '',
        }