"""PayPal state/fulfilment is committed atomically with the coin ledger."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import AppOrder, AppOrderEvent, AppPaymentCase, AppUser
from app.services.coin_wallet import adjust_coin_balance
from app.services.paypal_client import (
    PayPalClient,
    PayPalError,
    get_paypal_client,
    paypal_configured,
)


def money_cents(amount: dict[str, Any]) -> int:
    try:
        value = Decimal(amount["value"]) * 100
        if (
            not value.is_finite()
            or value < 0
            or value != value.to_integral_value()
            or amount["currency_code"] != "USD"
        ):
            raise ValueError()
        return int(value)
    except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
        raise PayPalError("Payment currency or amount does not match", 409) from exc


def validate_order(order: AppOrder, data: dict[str, Any]) -> dict[str, Any]:
    try:
        units = data["purchase_units"]
        if len(units) != 1:
            raise ValueError()
        unit = units[0]
        if (
            data["id"] != order.provider_order_id
            or data.get("intent") != "CAPTURE"
            or unit.get("custom_id") != str(order.id)
            or unit.get("invoice_id") != str(order.id)
            or unit.get("payee", {}).get("merchant_id") != settings.PAYPAL_MERCHANT_ID
            or money_cents(unit["amount"]) != order.amount
        ):
            raise ValueError()
        if data.get("payer", {}).get("address", {}).get("country_code") == "CN":
            raise ValueError()
        return unit
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise PayPalError("Payment order verification failed", 409) from exc


def lock_order(session: Session, order_id: uuid.UUID) -> AppOrder:
    return session.exec(
        select(AppOrder)
        .where(AppOrder.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def open_case(
    session: Session,
    order: AppOrder,
    *,
    kind: str,
    external_id: str,
    required_coins: int,
) -> AppPaymentCase:
    user = session.exec(
        select(AppUser)
        .where(AppUser.id == order.app_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    existing = session.exec(
        select(AppPaymentCase).where(
            AppPaymentCase.order_id == order.id,
            AppPaymentCase.kind == kind,
            AppPaymentCase.external_id == external_id,
        )
    ).first()
    if existing:
        return existing
    case = AppPaymentCase(
        order_id=order.id,
        app_user_id=order.app_user_id,
        kind=kind,
        external_id=external_id,
        required_coins=required_coins,
    )
    session.add(case)
    user.payment_hold = True
    session.add(user)
    return case


def apply_order_state(
    session: Session, order_id: uuid.UUID, data: dict[str, Any]
) -> AppOrder:
    order = lock_order(session, order_id)
    unit = validate_order(order, data)
    captures = unit.get("payments", {}).get("captures", [])
    now = datetime.now(UTC)
    if len(captures) > 1:
        raise PayPalError("Multiple captures require manual review", 409)
    if captures:
        capture = captures[0]
        if not capture.get("id") or money_cents(capture["amount"]) != order.amount:
            raise PayPalError("Capture amount does not match", 409)
        if order.capture_id and order.capture_id != capture["id"]:
            raise PayPalError("Capture ID does not match", 409)
        order.capture_id = capture["id"]
        order.transaction_id = capture["id"]
        capture_status = capture.get("status")
        if capture_status in {"REFUNDED", "PARTIALLY_REFUNDED", "REVERSED"}:
            # If a webhook is lost, reconciliation still freezes the account.
            # Partial refunds need the verified event amount before recovery.
            kind = (
                "reversed"
                if capture_status == "REVERSED"
                else (
                    "refund_reconcile"
                    if capture_status == "REFUNDED"
                    else "refund_review"
                )
            )
            open_case(
                session,
                order,
                kind=kind,
                external_id=capture["id"],
                required_coins=(order.coin_quantity or 0) if order.fulfilled_at else 0,
            )
            order.status = "reversed" if capture_status == "REVERSED" else "refunded"
        elif capture_status == "COMPLETED" and order.status not in {
            "refunded",
            "reversed",
        }:
            if order.fulfilled_at is None:
                user = session.exec(
                    select(AppUser)
                    .where(AppUser.id == order.app_user_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).one()
                if user.payment_hold:
                    order.status = "payment_review"
                else:
                    adjust_coin_balance(
                        session=session,
                        app_user_id=order.app_user_id,
                        delta=order.coin_quantity or 0,
                        entry_type="recharge_credit",
                        order_id=order.id,
                        idempotency_key=f"paypal-credit:{order.id}",
                        reason=f"PayPal recharge: {order.product_id}",
                    )
                    order.fulfilled_at = now
                    order.paid_at = now
                    order.status = "paid"
            else:
                order.status = "paid"
        elif order.fulfilled_at is None and order.status not in {
            "refunded",
            "reversed",
        }:
            order.status = (
                "capture_pending" if capture_status == "PENDING" else "failed"
            )
    elif order.fulfilled_at is None and order.status not in {"refunded", "reversed"}:
        order.status = {
            "APPROVED": "approved",
            "CREATED": "created",
            "PAYER_ACTION_REQUIRED": "created",
            "VOIDED": "canceled",
        }.get(str(data.get("status")), "capture_pending")
    order.updated_at = now
    order.next_reconcile_at = now + timedelta(minutes=10 if order.fulfilled_at else 1)
    session.add(order)
    session.flush()
    return order


def confirm_order(
    session: Session,
    order: AppOrder,
    client: PayPalClient,
    *,
    capture_approved: bool = True,
) -> AppOrder:
    if (
        order.payment_environment != settings.PAYPAL_ENVIRONMENT
        or not order.provider_order_id
    ):
        raise PayPalError("Payment environment or order ID mismatch", 409)
    data = client.order_details(order.provider_order_id)
    validate_order(order, data)
    if data.get("status") == "APPROVED" and capture_approved:
        try:
            client.capture_order(order)
        except PayPalError:
            # A timed-out capture might still have taken payment. Read rather
            # than assume failure or create a second payment.
            data = client.order_details(order.provider_order_id)
            if data.get("status") != "COMPLETED":
                raise
        data = client.order_details(order.provider_order_id)
    result = apply_order_state(session, order.id, data)
    session.commit()
    session.refresh(result)
    return result


def _capture_reference(resource: dict[str, Any]) -> str | None:
    related = resource.get("supplementary_data", {}).get("related_ids", {})
    if related.get("capture_id"):
        return str(related["capture_id"])
    for link in resource.get("links", []):
        parsed = urlsplit(link.get("href", ""))
        if parsed.hostname in {
            "api.paypal.com",
            "api.sandbox.paypal.com",
            "api-m.paypal.com",
            "api-m.sandbox.paypal.com",
        } and parsed.path.startswith("/v2/payments/captures/"):
            return parsed.path.split("/")[4]
    transactions = resource.get("disputed_transactions", [])
    return transactions[0].get("seller_transaction_id") if transactions else None


def process_webhook(
    session: Session, event: dict[str, Any], client: PayPalClient
) -> None:
    event_id, event_type = event.get("id"), event.get("event_type")
    resource = event.get("resource", {})
    if (
        not isinstance(event_id, str)
        or len(event_id) > 255
        or not isinstance(event_type, str)
        or len(event_type) > 100
    ):
        raise HTTPException(422, "Invalid payment event")
    related_id = (
        resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
    )
    capture_id = _capture_reference(resource)
    if event_type.startswith("CHECKOUT.ORDER."):
        related_id = resource.get("id")
    if event_type in {
        "PAYMENT.CAPTURE.COMPLETED",
        "PAYMENT.CAPTURE.PENDING",
        "PAYMENT.CAPTURE.DENIED",
        "PAYMENT.CAPTURE.REVERSED",
    }:
        capture_id = resource.get("id")
    filters = [
        AppOrder.provider == "paypal",
        AppOrder.payment_environment == settings.PAYPAL_ENVIRONMENT,
    ]
    if related_id:
        order = session.exec(
            select(AppOrder).where(*filters, AppOrder.provider_order_id == related_id)
        ).first()
    elif capture_id:
        order = session.exec(
            select(AppOrder).where(*filters, AppOrder.capture_id == capture_id)
        ).first()
    else:
        order = None
    # Do external reads outside the transaction's order/user locks.
    remote = (
        client.order_details(order.provider_order_id)
        if order and order.provider_order_id
        else None
    )
    # Global event lock also deduplicates unassociated verified events.
    from sqlalchemy import text

    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "paypal-event:" + event_id},
    )
    previous = session.exec(
        select(AppOrderEvent).where(
            AppOrderEvent.provider == "paypal", AppOrderEvent.event_id == event_id
        )
    ).first()
    if previous and (previous.order_id is not None or order is None):
        return
    if order:
        order = lock_order(session, order.id)
        if remote:
            validate_order(order, remote)
        if event_type in {
            "PAYMENT.CAPTURE.REFUNDED",
            "PAYMENT.CAPTURE.REVERSED",
        } or event_type.startswith("CUSTOMER.DISPUTE."):
            if event_type == "PAYMENT.CAPTURE.REFUNDED":
                cents = money_cents(resource.get("amount", {}))
                if (
                    not order.amount
                    or cents > order.amount
                    or resource.get("status") != "COMPLETED"
                ):
                    raise PayPalError("Refund requires verification", 409)
                required = (
                    ((order.coin_quantity or 0) * cents + order.amount - 1)
                    // order.amount
                    if order.fulfilled_at
                    else 0
                )
                kind = "refund"
                order.status = "refunded"
            elif event_type == "PAYMENT.CAPTURE.REVERSED":
                required = (order.coin_quantity or 0) if order.fulfilled_at else 0
                kind = "reversed"
                order.status = "reversed"
            else:
                required = (order.coin_quantity or 0) if order.fulfilled_at else 0
                kind = "dispute"
            open_case(
                session,
                order,
                kind=kind,
                external_id=str(resource.get("id", event_id)),
                required_coins=required,
            )
            session.add(order)
        elif remote:
            apply_order_state(session, order.id, remote)
    # Keep the minimum audit envelope, not payer names, addresses, or emails.
    if previous:
        previous.order_id = order.id if order else None
        previous.status = order.status if order else "unassociated"
        session.add(previous)
    else:
        safe_resource = {
            key: resource[key]
            for key in (
                "id",
                "status",
                "amount",
            )
            if key in resource
        }
        # Replay needs identifiers only, never links or nested payer data.
        safe_resource["supplementary_data"] = {
            "related_ids": {"order_id": related_id, "capture_id": capture_id}
        }
        safe_event = {
            "id": event_id,
            "event_type": event_type,
            "payment_environment": settings.PAYPAL_ENVIRONMENT,
            "resource": safe_resource,
        }
        session.add(
            AppOrderEvent(
                order_id=order.id if order else None,
                provider="paypal",
                event_id=event_id,
                event_type=event_type,
                status=order.status if order else "unassociated",
                transaction_id=capture_id,
                raw_payload=json.dumps(safe_event),
            )
        )
    session.commit()


def reconcile_paypal_orders() -> int:
    if not paypal_configured():
        return 0
    from app.core.db import engine

    processed = 0
    client = get_paypal_client()
    try:
        with Session(engine) as session:
            now = datetime.now(UTC)
            orders = session.exec(
                select(AppOrder)
                .where(
                    AppOrder.provider == "paypal",
                    AppOrder.payment_environment == settings.PAYPAL_ENVIRONMENT,
                    col(AppOrder.provider_order_id).is_not(None),
                    col(AppOrder.next_reconcile_at) <= now,
                )
                .order_by(col(AppOrder.next_reconcile_at))
                .limit(20)
            ).all()
            ids = [order.id for order in orders]
            session.rollback()
            for order_id in ids:
                order = session.get(AppOrder, order_id)
                if order is None:
                    continue
                try:
                    confirm_order(session, order, client)
                    processed += 1
                except PayPalError, ValueError:
                    session.rollback()
                    order = lock_order(session, order_id)
                    order.next_reconcile_at = datetime.now(UTC) + timedelta(minutes=5)
                    session.add(order)
                    session.commit()
            events = session.exec(
                select(AppOrderEvent)
                .where(
                    AppOrderEvent.provider == "paypal",
                    col(AppOrderEvent.order_id).is_(None),
                    AppOrderEvent.status == "unassociated",
                )
                .limit(20)
            ).all()
            for event in events:
                try:
                    envelope = json.loads(event.raw_payload)
                    if (
                        envelope.get("payment_environment")
                        != settings.PAYPAL_ENVIRONMENT
                    ):
                        continue
                    process_webhook(session, envelope, client)
                except PayPalError, ValueError:
                    session.rollback()
    finally:
        client.close()
    return processed


def resolve_case(
    session: Session,
    case_id: uuid.UUID,
    *,
    resolution: str,
    reason: str,
    admin_id: uuid.UUID,
    client: PayPalClient,
) -> AppPaymentCase:
    case = session.get(AppPaymentCase, case_id)
    if case is None:
        raise HTTPException(404, "Payment case not found")
    # Fetch external evidence before taking financial row locks.
    dispute = (
        client.dispute_details(case.external_id)
        if case.kind == "dispute" and case.status != "resolved"
        else {}
    )
    order = lock_order(session, case.order_id)
    user = session.exec(
        select(AppUser)
        .where(AppUser.id == case.app_user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    session.refresh(case)
    if case.status == "resolved":
        if case.resolution != resolution or case.reason != reason:
            raise HTTPException(409, "Case already resolved with another decision")
        return case
    if resolution == "dismiss":
        if case.kind != "dispute":
            raise HTTPException(409, "Refunds and reversals cannot be dismissed")
        if dispute.get("status") != "RESOLVED" or dispute.get(
            "dispute_outcome", {}
        ).get("outcome_code") not in {"RESOLVED_SELLER_FAVOUR", "CANCELED_BY_BUYER"}:
            raise HTTPException(
                409, "PayPal has not resolved this dispute in the merchant's favour"
            )
    else:
        if case.kind == "dispute":
            if (
                dispute.get("status") != "RESOLVED"
                or dispute.get("dispute_outcome", {}).get("outcome_code")
                != "RESOLVED_BUYER_FAVOUR"
            ):
                raise HTTPException(
                    409, "PayPal has not resolved this dispute in the buyer's favour"
                )
            if order.capture_id not in {
                item.get("seller_transaction_id")
                for item in dispute.get("disputed_transactions", [])
            }:
                raise HTTPException(
                    409, "Dispute transaction does not match this order"
                )
            cents = money_cents(
                dispute.get("dispute_outcome", {}).get("amount_refunded", {})
            )
            if not order.amount or not 0 < cents <= order.amount:
                raise HTTPException(409, "Verified dispute refund amount is required")
            case.required_coins = (
                ((order.coin_quantity or 0) * cents + order.amount - 1) // order.amount
                if order.fulfilled_at
                else 0
            )
        if case.kind == "refund_review":
            raise HTTPException(
                409,
                "A verified refund event is required to establish the partial refund amount",
            )
        recovered = session.exec(
            select(func.coalesce(func.sum(AppPaymentCase.recovered_coins), 0)).where(
                AppPaymentCase.order_id == order.id
            )
        ).one()
        required = min(
            case.required_coins, max((order.coin_quantity or 0) - int(recovered), 0)
        )
        if case.kind == "dispute":
            # A resolved dispute can describe the same cash refund as a webhook.
            required = max(case.required_coins - int(recovered), 0)
        if required:
            adjust_coin_balance(
                session=session,
                app_user_id=user.id,
                delta=-required,
                entry_type="recharge_recovery",
                order_id=order.id,
                admin_user_id=admin_id,
                idempotency_key=f"paypal-case:{case.id}",
                reason=f"Payment recovery: {case.external_id}",
            )
        case.recovered_coins = required
    case.status, case.resolution, case.reason = "resolved", resolution, reason
    case.resolved_by, case.resolved_at = admin_id, datetime.now(UTC)
    session.add(case)
    session.flush()
    # Verified refund/reversal resolves redundant reconciliation review cases.
    if case.kind in {"refund", "refund_reconcile", "reversed"}:
        for review in session.exec(
            select(AppPaymentCase).where(
                AppPaymentCase.order_id == order.id,
                col(AppPaymentCase.kind).in_(("refund_review", "refund_reconcile")),
                AppPaymentCase.status == "open",
            )
        ).all():
            if review.id == case.id:
                continue
            review.status, review.reason, review.resolution = (
                "resolved",
                reason,
                "recover",
            )
            review.resolved_by, review.resolved_at = admin_id, case.resolved_at
            session.add(review)
        session.flush()
    remaining = session.exec(
        select(func.count())
        .select_from(AppPaymentCase)
        .where(AppPaymentCase.app_user_id == user.id, AppPaymentCase.status == "open")
    ).one()
    user.payment_hold = bool(remaining)
    session.add(user)
    return case
