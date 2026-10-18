"""Bounded HK expansion; isolated database and fake providers only."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from app.core.config import settings
from app.models import AppOrder, AppUserIdentity
from tests.api.routes.test_payment_only_acceptance import (
    AUTH,
    CONFIG,
    ORDERS,
    create,
    headers,
)
from tests.api.routes.test_payment_only_acceptance import (
    no_real_http as no_real_http,
)
from tests.api.routes.test_payment_only_acceptance import (
    payment_only as payment_only,
)
from tests.api.routes.test_paypal_commerce import signed_headers


@pytest.mark.parametrize("country", ["CN", "HK"])
def test_signed_scope_same_identity_same_slot_same_deadline(
    client, db, payment_only, country
):
    _, user_id, _, _, fake = payment_only
    deadline = settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
    anonymous = client.get(
        CONFIG, headers=signed_headers(CONFIG, "GET", country)
    ).json()
    assert anonymous["payment_only_sign_in_enabled"]
    assert not anonymous["recharge_enabled"]
    assert not anonymous["registration_enabled"]
    config = client.get(CONFIG, headers=headers(CONFIG, "GET", country=country)).json()
    assert config["payment_only_acceptance_allowed"] and config["recharge_enabled"]
    assert config["country"] == country
    assert config["region_allowed"] is (country == "HK")
    assert datetime.fromisoformat(config["payment_only_expires_at"]) == deadline
    assert config["products"] == [
        {"product_id": "coins_100", "coins": 100, "amount": 599, "currency": "USD"}
    ]
    assert not client.post(AUTH, headers=headers(AUTH, country=country)).json()[
        "is_new_user"
    ]
    key = str(uuid.uuid4())
    first = create(client, key=key, country=country)
    assert first.status_code == 200
    other = "HK" if country == "CN" else "CN"
    assert create(client, key=key, country=other).json()["id"] == first.json()["id"]
    assert create(client, country=other).status_code == 409
    assert fake.create_calls == 1
    orders = db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).all()
    assert len(orders) == 1
    assert (orders[0].amount, orders[0].currency, orders[0].coin_quantity) == (
        599,
        "USD",
        100,
    )
    path = f"{ORDERS}/{orders[0].id}/checkout"
    assert (
        client.get(path, headers=headers(path, "GET", country=other)).status_code == 200
    )
    assert settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT == deadline


@pytest.mark.parametrize("country", ["US", "MY", "SG", "XX", "TW", "MO"])
def test_other_signed_countries_gain_no_payment_entitlement(
    client, payment_only, country
):
    config = client.get(CONFIG, headers=headers(CONFIG, "GET", country=country)).json()
    assert not config["payment_only_sign_in_enabled"]
    assert not config["payment_only_acceptance_allowed"]
    assert not config["registration_enabled"] and not config["recharge_enabled"]
    assert create(client, country=country).status_code == 403
    assert payment_only[-1].create_calls == 0


@pytest.mark.parametrize("proof", ["bare", "tampered", "stale", "wrong-path"])
def test_hk_requires_authentic_fresh_bound_edge_signature(client, payment_only, proof):
    h = headers(ORDERS, country="HK", key=str(uuid.uuid4()))
    if proof == "bare":
        h = {
            "Authorization": h["Authorization"],
            "Idempotency-Key": h["Idempotency-Key"],
        }
        h["CF-IPCountry"] = "HK"
    elif proof == "tampered":
        h["x-vireal-edge-signature"] = "0" * 64
    elif proof == "stale":
        h.update(signed_headers(ORDERS, "POST", "HK", timestamp="1"))
    else:
        h.update(signed_headers(CONFIG, "POST", "HK"))
    assert (
        client.post(ORDERS, headers=h, json={"product_id": "coins_100"}).status_code
        == 403
    )
    assert payment_only[-1].create_calls == 0


def test_hk_does_not_register_another_user_or_extend_expiry(
    client, db, payment_only, monkeypatch
):
    clerk, _, _, _, fake = payment_only
    original = clerk.claims
    clerk.claims = replace(original, subject=f"user_{uuid.uuid4().hex}")
    assert client.post(AUTH, headers=headers(AUTH, country="HK")).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()
    assert create(client, country="HK").status_code in {401, 403}
    clerk.claims = original
    monkeypatch.setattr(
        settings,
        "APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT",
        datetime.now(UTC) - timedelta(seconds=1),
    )
    config = client.get(CONFIG, headers=headers(CONFIG, "GET", country="HK")).json()
    assert not config["payment_only_sign_in_enabled"]
    assert (
        not config["payment_only_acceptance_allowed"] and not config["recharge_enabled"]
    )
    assert create(client, country="HK").status_code == 403
    assert fake.create_calls == 0
