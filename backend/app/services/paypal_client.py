"""Single-merchant PayPal REST client. No caller-controlled API hosts."""

import json
import time
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings

PRODUCTS = {
    "coins_100": (100, 599),
    "coins_220": (220, 1199),
    "coins_500": (500, 2499),
}


class PayPalError(Exception):
    def __init__(
        self,
        message: str = "Payment confirmation unavailable; please retry",
        status_code: int = 502,
    ):
        super().__init__(message)
        self.status_code = status_code


def paypal_configured() -> bool:
    return bool(
        all(
            (
                settings.PAYPAL_CLIENT_ID,
                settings.PAYPAL_CLIENT_SECRET,
                settings.PAYPAL_MERCHANT_ID,
                settings.PAYPAL_WEBHOOK_ID,
            )
        )
        and not (
            settings.ENVIRONMENT == "production"
            and settings.PAYPAL_ENVIRONMENT != "live"
        )
    )


class PayPalClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        if not paypal_configured():
            raise PayPalError("Payment service is not configured", 503)
        self.base_url = (
            "https://api-m.paypal.com"
            if settings.PAYPAL_ENVIRONMENT == "live"
            else "https://api-m.sandbox.paypal.com"
        )
        self.http = httpx.Client(
            timeout=settings.PAYPAL_REQUEST_TIMEOUT_SECONDS,
            transport=transport,
            follow_redirects=False,
        )
        self.access_token: str | None = None
        self.expires_at = 0.0

    def close(self) -> None:
        self.http.close()

    def _token(self) -> str:
        if self.access_token and time.monotonic() < self.expires_at:
            return self.access_token
        try:
            response = self.http.post(
                self.base_url + "/v1/oauth2/token",
                auth=(
                    settings.PAYPAL_CLIENT_ID or "",
                    settings.PAYPAL_CLIENT_SECRET or "",
                ),
                data={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            self.expires_at = time.monotonic() + max(
                int(data.get("expires_in", 300)) - 30, 0
            )
            return str(self.access_token)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise PayPalError() from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        content: bytes | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": "Bearer " + self._token(),
            "Content-Type": "application/json",
        }
        if request_id:
            headers["PayPal-Request-Id"] = request_id
            headers["Prefer"] = "return=representation"
        try:
            response = self.http.request(
                method,
                self.base_url + path,
                headers=headers,
                json=data,
                content=content,
            )
            if response.status_code >= 400:
                raise PayPalError(
                    status_code=409
                    if response.status_code in (400, 403, 404, 422)
                    else 502
                )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise PayPalError()
            return result
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise PayPalError() from exc

    def create_order(self, order: Any) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v2/checkout/orders",
            request_id=str(order.id),
            data={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "custom_id": str(order.id),
                        "invoice_id": str(order.id),
                        "description": f"Vireal: {order.coin_quantity} video-generation credits",
                        "payee": {"merchant_id": settings.PAYPAL_MERCHANT_ID},
                        "amount": {
                            "currency_code": "USD",
                            "value": f"{order.amount // 100}.{order.amount % 100:02d}",
                        },
                    }
                ],
                "payment_source": {
                    "paypal": {
                        "experience_context": {"shipping_preference": "NO_SHIPPING"}
                    }
                },
            },
        )

    def order_details(self, provider_id: str) -> dict[str, Any]:
        return self._request(
            "GET", "/v2/checkout/orders/" + quote(provider_id, safe="")
        )

    def capture_order(self, order: Any) -> dict[str, Any]:
        request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vireal:capture:{order.id}"))
        return self._request(
            "POST",
            "/v2/checkout/orders/"
            + quote(order.provider_order_id, safe="")
            + "/capture",
            data={},
            request_id=request_id,
        )

    def dispute_details(self, dispute_id: str) -> dict[str, Any]:
        return self._request(
            "GET", "/v1/customer/disputes/" + quote(dispute_id, safe="")
        )

    def verify_webhook(self, raw_body: bytes, headers: Any) -> bool:
        names = {
            "transmission_id": "paypal-transmission-id",
            "transmission_time": "paypal-transmission-time",
            "cert_url": "paypal-cert-url",
            "auth_algo": "paypal-auth-algo",
            "transmission_sig": "paypal-transmission-sig",
        }
        data = {key: headers.get(name) for key, name in names.items()}
        if not all(data.values()):
            return False
        data["webhook_id"] = settings.PAYPAL_WEBHOOK_ID
        # Preserve the original webhook JSON verbatim; never fetch cert_url.
        prefix = json.dumps(data).encode()[:-1]
        body = prefix + b', "webhook_event": ' + raw_body + b"}"
        result = self._request(
            "POST", "/v1/notifications/verify-webhook-signature", content=body
        )
        return result.get("verification_status") == "SUCCESS"


def get_paypal_client() -> PayPalClient:
    return PayPalClient()
