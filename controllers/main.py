# -*- coding: utf-8 -*-
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)


class CdekFrontendApi(http.Controller):
    """Public JSON endpoints consumed by the checkout widgets."""


    @staticmethod
    def _json_error(message, code="SERVER_ERROR"):
        """Return a uniform error dict that the OWL service can display."""
        return {"error": True, "message": message, "code": code}

    def _get_client(self, carrier_id=None):
        """Return a configured :class:`cdek_request.CdekRequest` instance."""
        settings = request.env["res.config.settings"].sudo()
        carrier = None
        if carrier_id:
            carrier = request.env["delivery.carrier"].sudo().browse(int(carrier_id))
        client = settings._get_cdek_client(carrier=carrier if carrier and carrier.exists() else None)
        if not client:
            raise UserError(_("CDEK API credentials are not configured."))
        return client


    @http.route("/cdek/city/search", type="json", auth="public", methods=["POST"], csrf=False)
    def city_search(self, query=None, limit=10, **_):
        """Return a list of cities for the autocomplete widget."""
        if not query:
            return []
        try:
            client = self._get_client()
            cities = client.get_cities({"q": query, "size": int(limit)})
            return [
                {
                    "code": str(c.get("code")),
                    "city": c.get("city"),
                    "region": c.get("region"),
                    "country_code": c.get("country_code"),
                    "country": c.get("country"),
                    "lat": c.get("latitude"),
                    "lon": c.get("longitude"),
                }
                for c in (cities or [])
            ]
        except Exception as e:
            _logger.exception("CDEK city search failed: %s", e)
            return self._json_error(str(e), "CITY_SEARCH_ERROR")

    @http.route("/cdek/config/yandex_key", type="json", auth="public", methods=["POST"], csrf=False)
    def yandex_key(self, **_):
        """Return Yandex.Maps API key if it is set in *System Parameters*."""
        try:
            key = request.env["ir.config_parameter"].sudo().get_param("cdek.yandex_maps_api_key")
            return key or None
        except Exception as e:
            _logger.exception("Cannot fetch Yandex key: %s", e)
            return self._json_error(_("Failed to obtain API key."), "YANDEX_KEY_ERROR")

    @http.route("/cdek/pvz/search", type="json", auth="public", methods=["POST"], csrf=False)
    def pvz_search(self, city_code=None, delivery_type="PVZ", limit=300, **_):
        """Return pickup points for the given *city_code*."""
        if not city_code:
            return []
        try:
            client = self._get_client()
            params = {
                "city_code": int(city_code),
                "type": delivery_type.upper() if delivery_type else None,
                "size": int(limit),
            }
            points = client.get_delivery_points(params=params)
            res = []
            for p in (points or []):
                loc = p.get("location", {})
                res.append(
                    {
                        "code": p.get("code"),
                        "name": p.get("name"),
                        "address": loc.get("address"),
                        "address_full": loc.get("address_full"),
                        "city": loc.get("city"),
                        "work_time": p.get("work_time"),
                        "lat": loc.get("latitude"),
                        "lon": loc.get("longitude"),
                        "type": p.get("type"),
                        "owner_code": p.get("owner_code"),
                        "is_cash_allowed": p.get("have_cash") or p.get("is_cash_on_delivery"),
                        "is_card_allowed": p.get("have_card") or p.get("is_card_payment"),
                    }
                )
            return res
        except Exception as e:
            _logger.exception("CDEK PVZ search failed: %s", e)
            return self._json_error(str(e), "PVZ_SEARCH_ERROR")

    @http.route("/cdek/calc", type="json", auth="public", methods=["POST"], csrf=False)
    def calc(self, order_id=None, carrier_id=None, cdek_city_code_to=None, cdek_pvz_code=None, **_):
        """Calculate delivery price and transit time."""
        if not (order_id and carrier_id and cdek_city_code_to):
            return self._json_error(_("Missing parameters."), "CALC_PARAM_ERROR")

        order = request.env["sale.order"].sudo().browse(int(order_id))
        carrier = request.env["delivery.carrier"].sudo().browse(int(carrier_id))

        if not order.exists():
            return self._json_error(_("Order not found."), "ORDER_NOT_FOUND")
        if not carrier.exists() or carrier.delivery_type != "cdek":
            return self._json_error(_("Invalid carrier."), "CARRIER_INVALID")

        order_vals = {"cdek_pvz_code": cdek_pvz_code if cdek_pvz_code else False}
        if order_vals:
            order.write(order_vals)

        try:
            rate = carrier.cdek_rate_shipment(order)
            if not rate.get("success"):
                return self._json_error(rate.get("error_message", _("Rating failed.")), "CALC_ERROR")

            return {
                "price": rate["price"],
                "currency_symbol": order.currency_id.symbol or request.env.company.currency_id.symbol,
                "term_days_min": rate.get("delivery_period_min") or rate.get("delivery_time_min"),
                "term_days_max": rate.get("delivery_period_max") or rate.get("delivery_time_max"),
                "warning_message": rate.get("warning_message"),
            }
        except Exception as e:
            _logger.exception("CDEK calc failed: %s", e)
            return self._json_error(str(e), "CALC_EXCEPTION")


    @http.route(
        "/shop/cdek/update_delivery",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def update_delivery(
        self,
        order_id=None,
        carrier_id=None,
        delivery_type=None,
        cdek_city_code=None,
        cdek_city_name=None,
        cdek_pvz_code=None,
        cdek_pvz_address=None,
        **_,
    ):
        """Persist the chosen carrier & PVZ and recalculate totals."""
        if not order_id or not carrier_id:
            return self._json_error(_("Missing parameters."), "UPDATE_PARAM_ERROR")

        order = request.env["sale.order"].sudo().browse(int(order_id))
        carrier = request.env["delivery.carrier"].sudo().browse(int(carrier_id))

        if not order.exists():
            return self._json_error(_("Order not found."), "ORDER_NOT_FOUND")
        if not carrier.exists() or carrier.delivery_type != "cdek":
            return self._json_error(_("Invalid carrier."), "CARRIER_INVALID")

        vals = {
            "carrier_id": carrier.id,
            "cdek_pvz_code": cdek_pvz_code if delivery_type == "pvz" else False,
        }
        if cdek_city_code:
            vals.update({
                "partner_shipping_id_city": cdek_city_name,
            })
        order.write(vals)

        try:
            order._remove_delivery_line()
            price_dict = carrier.rate_shipment(order)
            order.set_delivery_line(carrier, price_dict["price"])
            return {"success": True}
        except (UserError, AccessError) as e:
            _logger.warning("User error updating delivery: %s", e)
            return self._json_error(str(e), "USER_ERROR")
        except Exception as e:
            _logger.exception("Unexpected error updating delivery: %s", e)
            return self._json_error(_("Server error."), "SERVER_ERROR")
