"""Explicit, once-only replacement of a provider-verified VOIDED Live order.

404, elapsed time and human no-charge reports alone never grant replacement.
This module never captures, cancels, refunds or credits a payment.
"""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import (
    AppAdminOperationLog,
    AppCoinLedger,
    AppOrder,
    AppPayPalReplacement,
    AppPayPalReplacementApproval,
    AppUser,
    AppUserIdentity,
    User,
)
from app.services.commercial_access import (
    PAYMENT_ONLY_EMAIL,
    payment_only_acceptance_enabled,
)
from app.services.paypal_client import PayPalClient, PayPalError


def require_replacement_mode() -> None:
    if (
        not settings.APP_PAYMENT_ONLY_REPLACEMENT_ENABLED
        or not payment_only_acceptance_enabled()
    ):
        raise HTTPException(403, "Replacement is not authorized or has expired")


def grant_for_user(session: Session, user_id: uuid.UUID) -> AppPayPalReplacement | None:
    return session.exec(
        select(AppPayPalReplacement).where(AppPayPalReplacement.app_user_id == user_id)
    ).first()


def linked_grant(session: Session, order_id: uuid.UUID) -> AppPayPalReplacement | None:
    return session.exec(
        select(AppPayPalReplacement).where(
            or_(
                col(AppPayPalReplacement.original_order_id) == order_id,
                col(AppPayPalReplacement.replacement_order_id) == order_id,
            )
        )
    ).first()


def lock_beneficiary(session: Session, user_id: uuid.UUID) -> AppUser:
    user = session.exec(
        select(AppUser)
        .where(AppUser.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if user.status != "active" or user.deleted_at or user.payment_hold:
        raise HTTPException(409, "Account requires review; do not pay again")
    return user


def require_clean_original(session: Session, order: AppOrder) -> None:
    if (
        order.provider != "paypal"
        or order.payment_environment != "live"
        or order.product_id != "coins_100"
        or (order.amount, order.currency, order.coin_quantity) != (599, "USD", 100)
        or order.status not in {"created", "canceled"}
        or not order.provider_order_id
        or order.capture_id
        or order.transaction_id
        or order.fulfilled_at
        or order.paid_at
        or session.exec(
            select(AppCoinLedger.id).where(AppCoinLedger.order_id == order.id)
        ).first()
    ):
        raise HTTPException(409, "Original payment is not safely replaceable")


def verify_voided(order: AppOrder, client: PayPalClient) -> None:
    from app.services.paypal_orders import validate_order

    try:
        data = client.order_details(str(order.provider_order_id))
        unit = validate_order(order, data)
        payments = unit.get("payments", {})
        if (
            data.get("status") != "VOIDED"
            or not isinstance(payments, dict)
            or not isinstance(payments.get("captures", []), list)
            or not isinstance(payments.get("authorizations", []), list)
            or payments.get("captures")
            or payments.get("authorizations")
        ):
            raise ValueError()
    except (PayPalError, KeyError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            409,
            "Provider must explicitly confirm VOIDED with no payment; 404 is not evidence",
        ) from exc


def valid_grant(session: Session, grant: AppPayPalReplacement, *, unused: bool) -> bool:
    expires = settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
    user = session.get(AppUser, grant.app_user_id)
    identity = session.exec(
        select(AppUserIdentity).where(
            AppUserIdentity.app_user_id == grant.app_user_id,
            AppUserIdentity.subject == grant.subject,
            AppUserIdentity.issuer == grant.issuer,
        )
    ).first()
    return bool(
        settings.APP_PAYMENT_ONLY_REPLACEMENT_ENABLED
        and payment_only_acceptance_enabled()
        and grant.app_user_id == settings.APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID
        and grant.subject == settings.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT
        and grant.issuer.rstrip("/") == str(settings.CLERK_ISSUER_URL).rstrip("/")
        and expires
        and datetime.now(UTC) < grant.expires_at <= expires
        and user
        and user.status == "active"
        and not user.deleted_at
        and not user.payment_hold
        and identity
        and identity.email_verified
        and identity.primary_email.casefold() == PAYMENT_ONLY_EMAIL
        and (not unused or grant.replacement_order_id is None)
    )


def checkout_lineage(session: Session, order: AppOrder) -> bool:
    """Read-only lineage check; an old replaced order can never resume."""
    orders = session.exec(
        select(AppOrder.id).where(
            AppOrder.app_user_id == order.app_user_id,
            AppOrder.provider == "paypal",
            AppOrder.payment_environment == "live",
        )
    ).all()
    grant = grant_for_user(session, order.app_user_id)
    if grant is None:
        return orders == [order.id]
    if grant.replacement_order_id != order.id or not valid_grant(
        session, grant, unused=False
    ):
        return False
    old = session.get(AppOrder, grant.original_order_id)
    if (
        old is None
        or old.app_user_id != order.app_user_id
        or old.provider_order_id != grant.original_provider_order_id
    ):
        return False
    try:
        require_clean_original(session, old)
    except HTTPException:
        return False
    return len(orders) == 2 and set(orders) == {grant.original_order_id, order.id}


def approve_replacement(
    session: Session,
    order_id: uuid.UUID,
    body: AppPayPalReplacementApproval,
    admin: User,
    client: PayPalClient,
) -> AppPayPalReplacement:
    require_replacement_mode()
    user_id = settings.APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID
    if user_id is None:
        raise HTTPException(403, "No authorized beneficiary")
    lock_beneficiary(session, user_id)
    old = session.exec(
        select(AppOrder)
        .where(AppOrder.id == order_id, AppOrder.app_user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if old is None:
        raise HTTPException(404, "Original payment not found")
    existing = grant_for_user(session, user_id)
    if existing:
        if (
            existing.original_order_id == order_id
            and existing.idempotency_key == body.idempotency_key
            and existing.approved_by == admin.id
            and existing.reason == body.reason
            and existing.evidence_reference == body.evidence_reference
            and existing.expires_at == body.expires_at
        ):
            return existing
        raise HTTPException(409, "The lifetime replacement grant already exists")
    expiry = settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
    if (
        not body.expires_at.tzinfo
        or not expiry
        or not datetime.now(UTC) < body.expires_at <= expiry
    ):
        raise HTTPException(
            422, "Replacement expiry must fit the authorized payment window"
        )
    require_clean_original(session, old)
    original_provider_id = old.provider_order_id
    if not checkout_lineage(session, old):
        raise HTTPException(409, "Multiple order history requires manual review")
    verify_voided(old, client)
    session.expire_all()
    lock_beneficiary(session, user_id)
    session.refresh(old)
    require_replacement_mode()
    require_clean_original(session, old)
    if (
        old.app_user_id != user_id
        or old.provider_order_id != original_provider_id
        or not checkout_lineage(session, old)
    ):
        raise HTTPException(409, "Order ownership/history changed")
    grant = AppPayPalReplacement(
        app_user_id=user_id,
        original_order_id=old.id,
        original_provider_order_id=str(old.provider_order_id),
        approved_by=admin.id,
        subject=str(settings.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT),
        issuer=session.exec(
            select(AppUserIdentity.issuer).where(
                AppUserIdentity.app_user_id == user_id,
                AppUserIdentity.subject == settings.APP_PAYMENT_ONLY_ACCEPTANCE_SUBJECT,
            )
        ).first()
        or "",
        idempotency_key=body.idempotency_key,
        reason=body.reason,
        evidence_reference=body.evidence_reference,
        expires_at=body.expires_at,
    )
    # Identity and fresh expiry are checked before creating even a grant.
    if not valid_grant(session, grant, unused=True):
        raise HTTPException(403, "Verified beneficiary or window changed")
    session.add(grant)
    session.add(
        AppAdminOperationLog(
            admin_user_id=admin.id,
            admin_email=admin.email,
            action="paypal_replacement.approve",
            target_type="app_order",
            target_id=old.id,
            summary=body.reason,
            details_json=json.dumps(
                {
                    "grant_id": str(grant.id),
                    "provider_status": "VOIDED",
                    "evidence_reference": body.evidence_reference,
                    "merchant_checked_no_payment": True,
                    "payer_confirmed_no_payment": True,
                    "expires_at": body.expires_at.isoformat(),
                }
            ),
        )
    )
    session.commit()
    session.refresh(grant)
    return grant


def reserve_replacement(
    session: Session,
    old_id: uuid.UUID,
    owner_id: uuid.UUID,
    key: str,
    client: PayPalClient,
    may_create: Callable[[], bool],
) -> tuple[AppOrder, bool]:
    require_replacement_mode()
    lock_beneficiary(session, owner_id)
    grant = grant_for_user(session, owner_id)
    if (
        grant is None
        or grant.original_order_id != old_id
        or not valid_grant(session, grant, unused=False)
    ):
        raise HTTPException(403, "No current, explicit replacement authorization")
    if grant.replacement_order_id:
        new = session.get(AppOrder, grant.replacement_order_id)
        if (
            new
            and new.app_user_id == owner_id
            and new.payment_idempotency_key == key
            and new.provider_order_id
            and new.provider == "paypal"
            and new.payment_environment == "live"
            and (new.amount, new.currency, new.coin_quantity) == (599, "USD", 100)
            and checkout_lineage(session, new)
        ):
            return new, False
        raise HTTPException(
            409, "Replacement already reserved; never resubmit an unknown result"
        )
    old = session.exec(
        select(AppOrder)
        .where(AppOrder.id == old_id, AppOrder.app_user_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if not old or old.provider_order_id != grant.original_provider_order_id:
        raise HTTPException(409, "Original provider reference changed")
    require_clean_original(session, old)
    ids = session.exec(
        select(AppOrder.id).where(
            AppOrder.app_user_id == owner_id,
            AppOrder.provider == "paypal",
            AppOrder.payment_environment == "live",
        )
    ).all()
    if ids != [old_id]:
        raise HTTPException(409, "Unexpected lifetime order history")
    if session.exec(
        select(AppOrder.id).where(
            AppOrder.app_user_id == owner_id, AppOrder.payment_idempotency_key == key
        )
    ).first():
        raise HTTPException(409, "Use the replacement's own idempotency key")
    verify_voided(old, client)
    session.expire_all()
    session.refresh(old)
    session.refresh(grant)
    require_replacement_mode()
    require_clean_original(session, old)
    if (
        not valid_grant(session, grant, unused=True)
        or not may_create()
        or old.app_user_id != owner_id
        or old.provider_order_id != grant.original_provider_order_id
    ):
        raise HTTPException(409, "Replacement authorization changed")
    from app.services.video_quota import global_real_count

    admin = session.get(User, grant.approved_by)
    if admin is None or not admin.is_active or not admin.is_superuser:
        raise HTTPException(409, "Replacement approver is no longer authorized")
    if (
        global_real_count(session=session, now=datetime.now(UTC))
        >= settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS
    ):
        raise HTTPException(
            409, "Daily capacity exhausted; replacement recharge paused"
        )
    new = AppOrder(
        app_user_id=owner_id,
        provider="paypal",
        product_id="coins_100",
        payment_environment="live",
        payment_idempotency_key=key,
        amount=599,
        currency="USD",
        coin_quantity=100,
        next_reconcile_at=datetime.now(UTC),
    )
    session.add(new)
    session.flush()
    grant.replacement_order_id = new.id
    grant.consumed_at = datetime.now(UTC)
    session.add(grant)
    session.add(
        AppAdminOperationLog(
            admin_user_id=grant.approved_by,
            admin_email=str(admin.email),
            action="paypal_replacement.consume",
            target_type="app_order",
            target_id=old.id,
            summary="Beneficiary reserved the one approved replacement",
            details_json=json.dumps(
                {"grant_id": str(grant.id), "replacement_order_id": str(new.id)}
            ),
        )
    )
    # Commit reservation before provider I/O. Unknown provider result consumes it.
    session.commit()
    session.refresh(new)
    return new, True


def hold_conflicting_settlement(
    session: Session, order: AppOrder, data: dict[str, Any]
) -> None:
    """Keep genuine receipts, but never auto-credit contradictory old/new money."""
    grant = linked_grant(session, order.id)
    if grant is None:
        return
    old = session.get(AppOrder, grant.original_order_id)
    conflict = False
    if order.id == grant.original_order_id:
        unit = data["purchase_units"][0]
        payments = unit.get("payments", {})
        conflict = bool(
            data.get("status") in {"APPROVED", "COMPLETED"}
            or payments.get("captures")
            or payments.get("authorizations")
        )
    else:
        try:
            if (
                old is None
                or old.app_user_id != order.app_user_id
                or old.provider_order_id != grant.original_provider_order_id
            ):
                raise HTTPException(409)
            require_clean_original(session, old)
        except HTTPException:
            conflict = True
    if conflict:
        from app.services.paypal_orders import open_case

        open_case(
            session,
            order,
            kind="replacement_conflict",
            external_id=str(grant.id),
            required_coins=0,
        )


def guard_replacement_capture(
    session: Session, order: AppOrder, client: PayPalClient
) -> bool:
    grant = linked_grant(session, order.id)
    if grant is None:
        return True
    # Same user-first ordering as replacement reservation and settlement.
    lock_beneficiary(session, order.app_user_id)
    if grant.original_order_id == order.id:
        return False
    old = session.exec(
        select(AppOrder)
        .where(AppOrder.id == grant.original_order_id)
        .execution_options(populate_existing=True)
    ).one()
    if (
        old.app_user_id != order.app_user_id
        or old.provider_order_id != grant.original_provider_order_id
    ):
        raise HTTPException(409, "Original payment requires review")
    require_clean_original(session, old)
    verify_voided(old, client)
    return True
