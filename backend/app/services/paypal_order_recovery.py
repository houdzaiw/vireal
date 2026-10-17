"""Inspect the original payment without settling it or releasing its slot."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import (
    AppCoinLedger,
    AppOrder,
    AppPayPalOrderRecoveryPublic,
    AppUser,
)
from app.services.paypal_client import PayPalClient, PayPalError
from app.services.paypal_orders import money_cents, validate_order
from app.services.paypal_replacement import checkout_lineage

KNOWN_STATES = {
    "CREATED",
    "PAYER_ACTION_REQUIRED",
    "APPROVED",
    "COMPLETED",
    "VOIDED",
    "SAVED",
}


def inspect_original_order(
    session: Session,
    *,
    order_id: uuid.UUID,
    owner_id: uuid.UUID,
    client: PayPalClient,
    resume_authorized: Callable[[], bool],
) -> AppPayPalOrderRecoveryPublic:
    """Only provider GET + SQL reads. A 404/age is never proof of no charge.

    Even a genuine VOIDED order is only a candidate for separately authorized
    manual replacement. No flag, status, balance, idempotency key or lifetime
    reservation is ever changed here. Existing callbacks/Worker settle payments.
    """
    result = AppPayPalOrderRecoveryPublic(
        order_id=order_id, checked_at=datetime.now(UTC)
    )

    def current_order() -> AppOrder:
        session.expire_all()
        order = session.exec(
            select(AppOrder).where(
                AppOrder.id == order_id,
                AppOrder.app_user_id == owner_id,
                AppOrder.provider == "paypal",
                AppOrder.payment_environment == "live",
            )
        ).first()
        if order is None:
            raise HTTPException(404, "Payment order not found")
        return order

    def local_guard(order: AppOrder) -> bool:
        user = session.get(AppUser, owner_id)
        ledger = session.exec(
            select(AppCoinLedger).where(AppCoinLedger.order_id == order.id)
        ).all()
        if not user or user.status != "active" or user.deleted_at or user.payment_hold:
            result.reason_code = "account_review_required"
        elif not checkout_lineage(session, order):
            result.reason_code = "multiple_order_history"
        elif order.product_id != "coins_100" or (
            order.amount,
            order.currency,
            order.coin_quantity,
        ) != (599, "USD", 100):
            result.reason_code = "order_snapshot_mismatch"
        elif (
            order.status == "paid"
            and order.fulfilled_at
            and order.paid_at
            and order.capture_id
            and order.transaction_id == order.capture_id
            and len(ledger) == 1
            and ledger[0].delta == 100
            and ledger[0].app_user_id == owner_id
        ):
            result.decision = "credited"
            result.reason_code = "credits_received"
        elif (
            ledger
            or order.fulfilled_at
            or order.paid_at
            or order.capture_id
            or order.transaction_id
        ):
            result.reason_code = "financial_history_requires_review"
        elif not order.provider_order_id:
            result.reason_code = "provider_submission_unknown"
        else:
            return True
        return False

    order = current_order()
    if not local_guard(order):
        return result
    provider_id = order.provider_order_id
    data = None
    error = None
    try:
        data = client.order_details(str(provider_id))
    except PayPalError as exc:
        error = exc
    # A callback/hold/ownership change may have arrived during the GET.
    order = current_order()
    result.checked_at = datetime.now(UTC)
    if not local_guard(order):
        return result
    if order.provider_order_id != provider_id:
        result.reason_code = "provider_reference_changed"
        return result
    if error is not None:
        result.provider_http_status = error.provider_status_code
        result.reason_code = (
            "provider_order_unavailable"
            if error.provider_status_code == 404
            else "provider_query_unconfirmed"
        )
        return result
    try:
        if data is None:
            raise ValueError()
        unit = validate_order(order, data)
        payments = unit.get("payments", {})
        if not isinstance(payments, dict):
            raise ValueError()
        captures = payments.get("captures", [])
        authorizations = payments.get("authorizations", [])
        if not isinstance(captures, list) or not isinstance(authorizations, list):
            raise ValueError()
        status = data.get("status")
        if status not in KNOWN_STATES:
            raise ValueError()
        result.provider_order_status = status
        result.provider_http_status = 200
        if len(captures) > 1:
            raise ValueError()
        if captures:
            capture = captures[0]
            if (
                not isinstance(capture, dict)
                or not capture.get("id")
                or money_cents(capture["amount"]) != order.amount
            ):
                raise ValueError()
            if capture.get("status") in {"COMPLETED", "PENDING"}:
                result.decision = "settlement_pending"
                result.reason_code = "existing_payment_confirmation_pending"
            else:
                result.reason_code = "capture_requires_review"
            return result
        if authorizations or status == "APPROVED":
            result.decision = "settlement_pending"
            result.reason_code = "existing_payment_confirmation_pending"
            return result
        if status == "VOIDED" and order.status in {"created", "canceled"}:
            result.decision = "replacement_candidate"
            result.reason_code = "voided_order_needs_separate_authorization"
            result.replacement_candidate = True
            return result
        if status in {"CREATED", "PAYER_ACTION_REQUIRED"} and order.status == "created":
            if resume_authorized():
                result.decision = "resume_original"
                result.reason_code = "original_order_resumable"
                result.resume_allowed = True
            else:
                result.decision = "authorization_required"
                result.reason_code = "acceptance_authorization_required"
            return result
        result.reason_code = "provider_state_requires_review"
    except PayPalError, AttributeError, KeyError, TypeError, ValueError:
        result.reason_code = "provider_verification_failed"
    return result
