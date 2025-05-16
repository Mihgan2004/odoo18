# -*- coding: utf-8 -*-
import logging
import requests
from functools import cached_property
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from odoo import _
from odoo.exceptions import UserError
from ..const import CDEK_API_PROD_URL, CDEK_API_TEST_URL, CDEK_URLS, REQUEST_TIMEOUT_SECONDS

_logger = logging.getLogger(__name__)

class CdekRequest:

    def __init__(self, client_id, client_secret, test_mode=False, debug_logger=None):
        if not client_id or not client_secret:
            raise ValueError("CDEK client_id and client_secret are required.")
        self.base_url = (CDEK_API_TEST_URL if test_mode else CDEK_API_PROD_URL).rstrip("/") + "/"
        self.client_id = client_id
        self.client_secret = client_secret
        self.debug_logger = debug_logger
        self._session = None
        self._access_token = None

    def _get_session(self):
        if self._session is None:
            self._session = requests.Session()
            retries = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset(["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"])
            )
            adapter = HTTPAdapter(max_retries=retries)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        return self._session

    def _fetch_token(self):
        url = self.base_url + CDEK_URLS["token"]
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            resp = self._get_session().post(url, data=payload,
                                            headers=headers,
                                            timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise UserError(_("CDEK Auth Error: access_token missing in response."))
            return token
        except requests.exceptions.RequestException as e:
            _logger.error("CDEK Auth Error: %s\nResponse: %s", e, getattr(e, "response", None) and e.response.text)
            raise UserError(_("CDEK Auth Error: failed to fetch token: %s") % e)

    def _get_token(self):
        if not self._access_token:
            self._access_token = self._fetch_token()
        return self._access_token

    def _invalidate_token(self):
        _logger.info("CDEK: invalidating cached token")
        self._access_token = None

    def _request(self, method, endpoint_key, *, ep_params=None, query_params=None, json_payload=None, attempt=1):
        if endpoint_key not in CDEK_URLS:
            raise ValueError(f"Unknown endpoint key: {endpoint_key}")

        token = self._get_token()
        url = self.base_url + CDEK_URLS[endpoint_key].format(**(ep_params or {}))
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        resp = self._get_session().request(
            method, url,
            params=query_params,
            json=json_payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if resp.status_code == 401 and attempt == 1:
            self._invalidate_token()
            return self._request(method, endpoint_key,
                                 ep_params=ep_params,
                                 query_params=query_params,
                                 json_payload=json_payload,
                                 attempt=2)

        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            msg = _("CDEK API Error [%s]") % resp.status_code
            try:
                err = resp.json()
                details = err.get("errors") or \
                          (err.get("requests") and err["requests"][0].get("errors"))
                if isinstance(details, list):
                    msg += ": " + "; ".join(f"{d.get('code')}: {d.get('message')}" for d in details)
                elif err.get("message"):
                    msg += ": " + err["message"]
            except Exception:
                msg += f": {resp.text[:200]}"
            _logger.error("CDEK HTTPError: %s", msg)
            raise UserError(msg)

        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return resp.json()
        return resp.content 

    def get_cities(self, **params):
        return self._request("GET", "location_cities", query_params=params)

    def get_delivery_points(self, **params):
        return self._request("GET", "delivery_points", query_params=params)

    def calculate_tariff(self, payload):
        return self._request("POST", "calculator_tariff", json_payload=payload)

    def create_order(self, payload):
        return self._request("POST", "orders", json_payload=payload)

    def get_order_info(self, uuid):
        return self._request("GET", "order_by_uuid", ep_params={"uuid": uuid})

    def cancel_order(self, uuid):
        return self._request("DELETE", "order_cancel", ep_params={"uuid": uuid})

    def get_label(self, uuid, fmt="pdf"):
        return self._request("GET", "print_barcodes",
                             ep_params={"uuid": uuid},
                             query_params={"format": fmt})
