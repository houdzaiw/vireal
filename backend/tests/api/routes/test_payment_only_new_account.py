"""New beneficiary isolation; local PostgreSQL and fake providers only."""

import uuid
from dataclasses import replace

import pytest
from sqlmodel import delete, select

from app.core.config import settings
from app.models import (
    AppCoinLedger,
    AppOrder,
    AppOrderEvent,
    AppPaymentCase,
    AppUser,
    AppUserIdentity,
    AppUserSession,
)
from app.services import commercial_access
from app.services.app_identity import hash_clerk_session_id
from app.services.coin_wallet import get_coin_balance
from tests.api.routes.test_payment_only_acceptance import (
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

NEW_EMAIL = "li522903183@163.com"
FORMER_EMAIL = "li8483@yeah.net"


@pytest.fixture
def former_account(db, payment_only):
    clerk, _, _, _, fake = payment_only
    user = AppUser(account_type="clerk")
    db.add(user)
    db.flush()
    subject = f"user_former_{uuid.uuid4().hex}"
    session_id = f"session_former_{uuid.uuid4().hex}"
    identity = AppUserIdentity(
        app_user_id=user.id,
        issuer=clerk.claims.issuer,
        subject=subject,
        primary_email=FORMER_EMAIL,
        email_verified=True,
    )
    db.add(identity)
    db.add(
        AppUserSession(
            app_user_id=user.id,
            session_id_hash=hash_clerk_session_id(session_id),
        )
    )
    order = AppOrder(
        app_user_id=user.id,
        provider="paypal",
        product_id="coins_100",
        amount=599,
        currency="USD",
        coin_quantity=100,
        payment_environment="live",
        payment_idempotency_key=str(uuid.uuid4()),
    )
    order.provider_order_id = f"PAY-FORMER-{order.id}"
    db.add(order)
    db.commit()
    # Pre-existing remote fixture, not a call to create an order at a provider.
    fake.orders[order.provider_order_id] = {
        "id": order.provider_order_id,
        "intent": "CAPTURE",
        "status": "CREATED",
        "purchase_units": [
            {
                "custom_id": str(order.id),
                "invoice_id": str(order.id),
                "payee": {"merchant_id": "TEST-MERCHANT"},
                "amount": {"currency_code": "USD", "value": "5.99"},
            }
        ],
    }
    yield user.id, identity.id, order.id, subject, session_id
    db.rollback()
    db.execute(delete(AppOrderEvent).where(AppOrderEvent.order_id == order.id))
    db.execute(delete(AppPaymentCase).where(AppPaymentCase.app_user_id == user.id))
    db.execute(delete(AppCoinLedger).where(AppCoinLedger.app_user_id == user.id))
    db.delete(db.get(AppOrder, order.id))
    db.delete(db.get(AppUser, user.id))
    db.commit()


def test_new_target_has_its_own_single_slot_and_cannot_take_over_old_order(
    client, db, payment_only, former_account, monkeypatch
):
    clerk, user_id, _, _, fake = payment_only
    _, _, old_id, _, _ = former_account
    assert commercial_access.PAYMENT_ONLY_EMAIL == NEW_EMAIL
    assert clerk.profile.primary_email == NEW_EMAIL
    before = db.get(AppOrder, old_id).model_dump()

    def forbidden(*_args):
        pytest.fail("Cross-owner access must not reach the provider")

    monkeypatch.setattr(fake, "order_details", forbidden)
    monkeypatch.setattr(fake, "capture_order", forbidden)
    config = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert config["recharge_enabled"] and not config["payment_only_order_created"]
    assert config["payment_only_replacement_original_id"] is None
    assert config["payment_only_checkout_order_id"] is None
    listing = "/api/v1/app/orders"
    assert client.get(listing, headers=headers(listing, "GET")).json()["count"] == 0
    for path in (
        f"{listing}/{old_id}",
        f"{ORDERS}/{old_id}/checkout",
        f"{ORDERS}/{old_id}/recovery",
    ):
        assert client.get(path, headers=headers(path, "GET")).status_code == 404
    path = f"{ORDERS}/{old_id}/capture"
    assert client.post(path, headers=headers(path)).status_code == 404
    path = f"{ORDERS}/{old_id}/replacement"
    assert (
        client.post(path, headers=headers(path, key=str(uuid.uuid4()))).status_code
        == 403
    )

    response = create(client)
    assert response.status_code == 200, response.text
    new = response.json()
    assert new["app_user_id"] == str(user_id) and new["id"] != str(old_id)
    assert (new["amount"], new["currency"], new["coin_quantity"]) == (599, "USD", 100)
    assert create(client).status_code == 409
    assert fake.create_calls == 1
    db.expire_all()
    assert db.get(AppOrder, old_id).model_dump() == before
    assert get_coin_balance(session=db, app_user_id=user_id) == 0
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.app_user_id == user_id)
    ).first()


@pytest.mark.parametrize("provider", ["apple", "google"])
def test_payment_only_cannot_create_legacy_platform_order(
    client, db, payment_only, provider
):
    _, user_id, _, _, fake = payment_only
    path = "/api/v1/app/orders"
    assert (
        client.post(
            path,
            headers=headers(path),
            json={
                "provider": provider,
                "product_id": "coins_100",
                "amount": 599,
                "currency": "USD",
            },
        ).status_code
        == 403
    )
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == user_id)).first()
    assert fake.create_calls == 0


def test_former_verified_account_is_not_reenabled_by_reusing_old_binding(
    client, db, payment_only, former_account, monkeypatch
):
    clerk, _, _, _, fake = payment_only
    old_user, _, old_id, old_subject, old_session = former_account
    before = db.get(AppOrder, old_id).model_dump()
    clerk.claims = replace(clerk.claims, subject=old_subject, session_id=old_session)
    clerk.profile = replace(clerk.profile, primary_email=FORMER_EMAIL)
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT", old_subject)
    monkeypatch.setattr(settings, "APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID", old_user)
    config = client.get(CONFIG, headers=headers(CONFIG, "GET")).json()
    assert (
        not config["recharge_enabled"] and not config["payment_only_acceptance_allowed"]
    )
    assert create(client).status_code == 403
    assert fake.create_calls == 0
    db.expire_all()
    assert db.get(AppOrder, old_id).model_dump() == before


@pytest.mark.parametrize("closed", [False, True])
def test_late_old_payment_still_credits_original_owner_once_not_new_beneficiary(
    client, db, payment_only, former_account, monkeypatch, closed
):
    _, new_user, _, _, fake = payment_only
    old_user, _, old_id, _, _ = former_account
    old = db.get(AppOrder, old_id)
    # Model an already completed remote payment; no external API is reachable.
    fake.capture_order(old)
    event = {
        "id": f"WH-{uuid.uuid4()}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": f"CAP-{old_id}",
            "supplementary_data": {"related_ids": {"order_id": old.provider_order_id}},
        },
    }
    if closed:
        for key in (
            "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED",
            "PAYPAL_ENABLED",
            "APP_COMMERCE_TERMS_APPROVED",
        ):
            monkeypatch.setattr(settings, key, False)
    path = "/api/v1/webhooks/payments/paypal"
    for _ in range(2):
        assert client.post(path, json=event).status_code == 204
    db.expire_all()
    old = db.get(AppOrder, old_id)
    assert old.app_user_id == old_user and old.fulfilled_at and old.status == "paid"
    credits = db.exec(
        select(AppCoinLedger).where(AppCoinLedger.order_id == old_id)
    ).all()
    assert (
        len(credits) == 1
        and credits[0].app_user_id == old_user
        and credits[0].delta == 100
    )
    assert get_coin_balance(session=db, app_user_id=old_user) == 100
    assert get_coin_balance(session=db, app_user_id=new_user) == 0
    assert fake.create_calls == 0
    assert not db.exec(select(AppOrder).where(AppOrder.app_user_id == new_user)).first()
    assert not db.exec(
        select(AppCoinLedger).where(AppCoinLedger.app_user_id == new_user)
    ).first()
