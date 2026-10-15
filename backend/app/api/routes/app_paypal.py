import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from sqlalchemy import text
from sqlmodel import col, select

from app.api.deps import CurrentAppUser, SessionDep
from app.core.config import settings
from app.models import AppOrder, AppOrderPublic, AppPayPalOrderCreate
from app.services.commercial_access import (
    acceptance_request_allowed,
    controlled_registration_enabled,
    edge_country,
    lock_commercial_user,
    region_allowed,
    require_new_commerce_user,
    require_region,
)
from app.services.paypal_client import (
    PRODUCTS,
    PayPalError,
    get_paypal_client,
    paypal_configured,
)
from app.services.paypal_orders import confirm_order, lock_order
from app.services.video_quota import global_real_count, utc_day_bounds

router = APIRouter(prefix="/app/paypal", tags=["app paypal"])


@router.get("/config")
def payment_config(
    request: Request, response: Response, session: SessionDep
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    remaining = max(
        settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS
        - global_real_count(session=session, now=now),
        0,
    )
    allowed = region_allowed(request)
    acceptance_allowed = (
        acceptance_request_allowed(request)
        if settings.APP_LIVE_ACCEPTANCE_ENABLED
        else False
    )
    identity_allowed = not settings.APP_LIVE_ACCEPTANCE_ENABLED or acceptance_allowed
    return {
        "environment": settings.PAYPAL_ENVIRONMENT,
        "client_id": settings.PAYPAL_CLIENT_ID if paypal_configured() else None,
        "country": edge_country(request),
        "region_allowed": allowed,
        "registration_enabled": (
            settings.APP_PUBLIC_REGISTRATION_ENABLED or acceptance_allowed
        )
        and allowed,
        # This advertises only a private invitation landing page, not signup.
        # The verified primary email is checked again by the session endpoint.
        "controlled_registration_enabled": controlled_registration_enabled()
        and allowed,
        "recharge_enabled": settings.PAYPAL_ENABLED
        and paypal_configured()
        and allowed
        and identity_allowed
        and remaining > 0,
        "global_real_limit": settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS,
        "global_real_remaining": remaining,
        "resets_at": utc_day_bounds(now)[1],
        "support_email": str(settings.APP_SUPPORT_EMAIL),
        "products": [
            {"product_id": key, "coins": coins, "amount": amount, "currency": "USD"}
            for key, (coins, amount) in PRODUCTS.items()
        ],
    }


@router.post("/orders", response_model=AppOrderPublic)
def create_paypal_order(
    request: Request,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    body: AppPayPalOrderCreate,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=120)],
) -> AppOrderPublic:
    require_region(request)
    require_new_commerce_user(request)
    if body.product_id not in PRODUCTS:
        raise HTTPException(422, "Unknown recharge package")
    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"paypal-create:{current_app_user.id}:{idempotency_key}"},
    )
    order = session.exec(
        select(AppOrder).where(
            AppOrder.app_user_id == current_app_user.id,
            AppOrder.payment_idempotency_key == idempotency_key,
        )
    ).first()
    if order:
        if (
            order.product_id != body.product_id
            or order.payment_environment != settings.PAYPAL_ENVIRONMENT
        ):
            raise HTTPException(409, "Idempotency key belongs to another request")
        if order.provider_order_id:
            return AppOrderPublic.model_validate(order)
    if not settings.PAYPAL_ENABLED or not paypal_configured():
        raise HTTPException(503, "Recharge is not yet available / 充值尚未开放")
    if order is None:
        # Same lock as video submission: check and reserve/insert atomically.
        from app.api.routes.app_video_tasks import POC_BUDGET_LOCK_ID

        session.connection().execute(
            text("SELECT pg_advisory_xact_lock(:id)"), {"id": POC_BUDGET_LOCK_ID}
        )
        lock_commercial_user(session, current_app_user)
        now = datetime.now(UTC)
        if (
            global_real_count(session=session, now=now)
            >= settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS
        ):
            raise HTTPException(
                409, "Daily generation capacity is exhausted; recharge is paused"
            )
        # Bound abandoned orders per verified account; idempotent retries do not count.
        recent = session.exec(
            select(AppOrder).where(
                AppOrder.app_user_id == current_app_user.id,
                AppOrder.provider == "paypal",
                col(AppOrder.created_at) >= now - timedelta(minutes=10),
            )
        ).all()
        if len(recent) >= 5:
            raise HTTPException(429, "Too many payment orders; please wait")
        coins, amount = PRODUCTS[body.product_id]
        order = AppOrder(
            app_user_id=current_app_user.id,
            provider="paypal",
            product_id=body.product_id,
            payment_environment=settings.PAYPAL_ENVIRONMENT,
            payment_idempotency_key=idempotency_key,
            amount=amount,
            currency="USD",
            coin_quantity=coins,
            next_reconcile_at=now,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
    client = None
    try:
        client = get_paypal_client()
        result = client.create_order(order)
        provider_id = result.get("id")
        if (
            not isinstance(provider_id, str)
            or not provider_id
            or len(provider_id) > 255
        ):
            raise PayPalError()
        order = lock_order(session, order.id)
        if order.provider_order_id not in {None, provider_id}:
            raise PayPalError("Payment create returned conflicting order IDs", 409)
        order.provider_order_id = provider_id
        session.add(order)
        session.commit()
        session.refresh(order)
    except PayPalError as exc:
        session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    finally:
        if client:
            client.close()
    return AppOrderPublic.model_validate(order)


@router.post("/orders/{order_id}/capture", response_model=AppOrderPublic)
def capture_paypal_order(
    order_id: uuid.UUID, session: SessionDep, current_app_user: CurrentAppUser
) -> AppOrderPublic:
    # Existing approved payments must finish even after capacity/feature gates close.
    order = session.exec(
        select(AppOrder).where(
            AppOrder.id == order_id,
            AppOrder.app_user_id == current_app_user.id,
            AppOrder.provider == "paypal",
        )
    ).first()
    if order is None:
        raise HTTPException(404, "Payment order not found")
    client = None
    try:
        client = get_paypal_client()
        return AppOrderPublic.model_validate(confirm_order(session, order, client))
    except PayPalError as exc:
        session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    finally:
        if client:
            client.close()
