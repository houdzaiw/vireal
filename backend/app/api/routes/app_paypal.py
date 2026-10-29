import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from sqlalchemy import text
from sqlmodel import col, select

from app.api.deps import CurrentAppUser, SessionDep
from app.core.config import settings
from app.models import (
    AppOrder,
    AppOrderPublic,
    AppPayPalOrderCreate,
    AppPayPalOrderRecoveryPublic,
)
from app.services.commercial_access import (
    PAYMENT_ONLY_COUNTRIES,
    acceptance_request_allowed,
    controlled_cn_account_setup_enabled,
    controlled_registration_enabled,
    edge_country,
    internal_acceptance_enabled,
    lock_commercial_user,
    payment_only_acceptance_enabled,
    payment_only_order_created,
    payment_only_user,
    region_allowed,
    require_new_commerce_user,
    require_region,
)
from app.services.generation_acceptance import (
    generation_acceptance_mode_safe,
    generation_acceptance_task,
    generation_acceptance_user,
    generation_acceptance_window_open,
)
from app.services.paypal_client import (
    PRODUCTS,
    PayPalError,
    get_paypal_client,
    paypal_configured,
)
from app.services.paypal_order_recovery import inspect_original_order
from app.services.paypal_orders import confirm_order, lock_order, validate_order
from app.services.paypal_replacement import (
    checkout_lineage,
    grant_for_user,
    reserve_replacement,
    valid_grant,
    verify_voided,
)
from app.services.staging_login_acceptance import staging_sign_in_enabled
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
    staging_sign_in = staging_sign_in_enabled(request)
    cn_setup = controlled_cn_account_setup_enabled() and edge_country(request) == "CN"
    cn_setup_mode = settings.APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED
    payment_only = settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
    generation_mode = settings.APP_GENERATION_ACCEPTANCE_ENABLED
    generation_user = (
        generation_acceptance_user(request, session) if generation_mode else None
    )
    generation_task = (
        generation_acceptance_task(session, generation_user)
        if generation_user
        else None
    )
    payment_user = payment_only_user(request, session) if payment_only else None
    slot_used = bool(payment_user and payment_only_order_created(session, payment_user))
    grant = grant_for_user(session, payment_user.id) if payment_user else None
    replacement_ready = bool(grant and valid_grant(session, grant, unused=True))
    acceptance_allowed = (
        acceptance_request_allowed(request)
        if settings.APP_LIVE_ACCEPTANCE_ENABLED
        else False
    )
    identity_allowed = not settings.APP_LIVE_ACCEPTANCE_ENABLED or acceptance_allowed
    # Ordinary availability hints, never an entitlement or quota grant. Raw
    # private-mode switches still restrict commerce after expiry or invalidity.
    submissions_enabled = bool(
        settings.APP_VIDEO_SUBMISSIONS_ENABLED
        and allowed
        and identity_allowed
        and not generation_mode
        and not payment_only
        and not cn_setup_mode
    )
    return {
        "environment": settings.PAYPAL_ENVIRONMENT,
        "client_id": settings.PAYPAL_CLIENT_ID if paypal_configured() else None,
        "country": edge_country(request),
        "region_allowed": allowed,
        # A form hint only: subject/identity are checked by the session endpoint.
        "staging_sign_in_enabled": staging_sign_in,
        "staging_sign_in_expires_at": settings.APP_STAGING_LOGIN_ACCEPTANCE_EXPIRES_AT
        if staging_sign_in
        else None,
        "uploads_enabled": submissions_enabled,
        "generation_enabled": submissions_enabled,
        "generation_acceptance_mode": generation_mode,
        "generation_acceptance_sign_in_enabled": generation_acceptance_mode_safe()
        and edge_country(request) == "CN",
        "generation_acceptance_read_allowed": generation_user is not None,
        "generation_acceptance_allowed": bool(
            generation_user
            and not generation_task
            and generation_acceptance_window_open()
        ),
        "generation_acceptance_task_id": str(generation_task.id)
        if generation_task
        else None,
        "generation_acceptance_expires_at": settings.APP_GENERATION_ACCEPTANCE_EXPIRES_AT
        if generation_user
        else None,
        "controlled_account_setup_mode": cn_setup_mode,
        "controlled_account_setup_enabled": cn_setup,
        "controlled_account_setup_expires_at": settings.APP_CONTROLLED_CN_ACCOUNT_SETUP_EXPIRES_AT
        if cn_setup
        else None,
        # Only lets a private login landing page mount sign-in, never signup.
        # This is not an entitlement; upload/generation authenticate again.
        "internal_sign_in_enabled": internal_acceptance_enabled()
        and edge_country(request) == "CN",
        "payment_only_acceptance_mode": payment_only,
        # A private login form only; the URL and this hint confer no entitlement.
        "payment_only_sign_in_enabled": payment_only_acceptance_enabled()
        and edge_country(request) in PAYMENT_ONLY_COUNTRIES,
        "payment_only_acceptance_allowed": payment_user is not None,
        "payment_only_order_created": slot_used,
        "payment_only_replacement_original_id": str(grant.original_order_id)
        if grant and replacement_ready
        else None,
        "payment_only_checkout_order_id": str(grant.replacement_order_id)
        if grant
        and grant.replacement_order_id
        and valid_grant(session, grant, unused=False)
        else None,
        "payment_only_expires_at": settings.APP_PAYMENT_ONLY_ACCEPTANCE_EXPIRES_AT
        if payment_user
        else None,
        "registration_enabled": (
            settings.APP_PUBLIC_REGISTRATION_ENABLED or acceptance_allowed
        )
        and allowed
        and not payment_only
        and not cn_setup_mode
        and not generation_mode,
        # The raw generation mode is a kill switch even when expired/invalid.
        # This advertises only a private invitation landing page, not signup.
        # The verified primary email is checked again by the session endpoint.
        "controlled_registration_enabled": controlled_registration_enabled()
        and (cn_setup if cn_setup_mode else allowed)
        and not payment_only
        and not generation_mode,
        "recharge_enabled": settings.PAYPAL_ENABLED
        and not cn_setup_mode
        and not generation_mode
        and paypal_configured()
        and (payment_user is not None and not slot_used if payment_only else allowed)
        and identity_allowed
        and remaining > 0,
        "global_real_limit": settings.APP_GLOBAL_DAILY_REAL_SUBMISSIONS,
        "global_real_remaining": remaining,
        "resets_at": utc_day_bounds(now)[1],
        "support_email": str(settings.APP_SUPPORT_EMAIL),
        "products": [
            {"product_id": key, "coins": coins, "amount": amount, "currency": "USD"}
            for key, (coins, amount) in PRODUCTS.items()
            if not payment_only or key == "coins_100"
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
    payment_only = settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
    if payment_only:
        permitted = payment_only_user(request, session, verify_profile=True)
        if permitted is None or permitted.id != current_app_user.id:
            raise HTTPException(
                403, "Payment-only acceptance is unavailable for this account"
            )
        if body.product_id != "coins_100" or PRODUCTS.get("coins_100") != (100, 599):
            raise HTTPException(
                403, "Payment-only acceptance permits only USD 5.99 for 100 credits"
            )
    else:
        require_region(request)
        require_new_commerce_user(request)
    if body.product_id not in PRODUCTS:
        raise HTTPException(422, "Unknown recharge package")
    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"paypal-create:{current_app_user.id}:{idempotency_key}"},
    )
    if payment_only:
        # Preserve the same budget -> user lock order as video/new-order paths,
        # including requests already in flight during a configuration rollout.
        from app.api.routes.app_video_tasks import POC_BUDGET_LOCK_ID

        session.connection().execute(
            text("SELECT pg_advisory_xact_lock(:id)"), {"id": POC_BUDGET_LOCK_ID}
        )
        # Serialize all keys for the beneficiary before checking the lifetime
        # slot. The local reservation commits before provider I/O.
        lock_commercial_user(session, current_app_user)
        if not payment_only_acceptance_enabled():
            raise HTTPException(403, "Payment-only acceptance has expired")
    order = session.exec(
        select(AppOrder).where(
            AppOrder.app_user_id == current_app_user.id,
            AppOrder.payment_idempotency_key == idempotency_key,
        )
    ).first()
    if order:
        if payment_only and (
            order.provider != "paypal"
            or (order.amount, order.currency, order.coin_quantity) != (599, "USD", 100)
        ):
            raise HTTPException(
                409, "Existing order is not the permitted acceptance package"
            )
        if (
            order.product_id != body.product_id
            or order.payment_environment != settings.PAYPAL_ENVIRONMENT
        ):
            raise HTTPException(409, "Idempotency key belongs to another request")
        if order.provider_order_id:
            if (
                payment_only
                and (grant := grant_for_user(session, current_app_user.id))
                and grant.original_order_id == order.id
            ):
                raise HTTPException(
                    409, "Original order has a replacement grant; do not pay it"
                )
            return AppOrderPublic.model_validate(order)
        if payment_only:
            # A committed reservation with no provider ID may already have
            # created an order. Never rely on an unbounded provider dedup window
            # or resubmit it, even under the same application idempotency key.
            raise HTTPException(
                409,
                "The single acceptance order requires manual verification; do not pay again",
            )
    if not settings.PAYPAL_ENABLED or not paypal_configured():
        raise HTTPException(503, "Recharge is not yet available / 充值尚未开放")
    if order is None:
        if payment_only and payment_only_order_created(session, current_app_user):
            raise HTTPException(
                409, "The single acceptance order already exists; check its status"
            )
        # Same lock as video submission: check and reserve/insert atomically.
        from app.api.routes.app_video_tasks import POC_BUDGET_LOCK_ID

        session.connection().execute(
            text("SELECT pg_advisory_xact_lock(:id)"), {"id": POC_BUDGET_LOCK_ID}
        )
        lock_commercial_user(session, current_app_user)
        if payment_only and not payment_only_acceptance_enabled():
            raise HTTPException(403, "Payment-only acceptance has expired")
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


def _require_resumable_acceptance_order(session: SessionDep, order: AppOrder) -> None:
    if (
        order.payment_environment != "live"
        or order.product_id != "coins_100"
        or (order.amount, order.currency, order.coin_quantity) != (599, "USD", 100)
        or not order.provider_order_id
        or order.status != "created"
        or order.fulfilled_at
        or order.paid_at
        or order.capture_id
        or order.transaction_id
    ):
        raise HTTPException(
            409, "Check the original order status; do not create or pay another order"
        )
    if not checkout_lineage(session, order):
        raise HTTPException(
            409, "The original acceptance order requires manual verification"
        )


@router.get("/orders/{order_id}/checkout", response_model=AppOrderPublic)
def resume_paypal_checkout(
    order_id: uuid.UUID,
    request: Request,
    response: Response,
    session: SessionDep,
    current_app_user: CurrentAppUser,
) -> AppOrderPublic:
    """Read-only preflight for resuming the same controlled payment in the SDK.

    Never create/capture/cancel an order or apply provider state here. Approved
    or uncertain payments are left to the existing callback/reconciliation path.
    """
    response.headers["Cache-Control"] = "no-store"
    order = session.exec(
        select(AppOrder).where(
            AppOrder.id == order_id,
            AppOrder.app_user_id == current_app_user.id,
            AppOrder.provider == "paypal",
        )
    ).first()
    if order is None:
        raise HTTPException(404, "Payment order not found")
    permitted = payment_only_user(request, session, verify_profile=True)
    if permitted is None or permitted.id != current_app_user.id:
        raise HTTPException(403, "Payment-only acceptance is unavailable or expired")
    if not paypal_configured():
        raise HTTPException(
            503, "Payment service is unavailable; check the original order"
        )
    _require_resumable_acceptance_order(session, order)
    client = get_paypal_client()
    try:
        grant = grant_for_user(session, order.app_user_id)
        if grant:
            original = session.get(AppOrder, grant.original_order_id)
            if original is None:
                raise HTTPException(409, "Original payment requires review")
            verify_voided(original, client)
        data = client.order_details(str(order.provider_order_id))
        unit = validate_order(order, data)
        payments = unit.get("payments", {})
        if (
            data.get("status") not in {"CREATED", "PAYER_ACTION_REQUIRED"}
            or not isinstance(payments, dict)
            or payments.get("captures")
            or payments.get("authorizations")
        ):
            raise HTTPException(
                409, "The original payment cannot be restarted; refresh its status"
            )
        # Callback, hold and expiry changes during provider I/O must fail closed.
        session.expire_all()
        permitted = payment_only_user(request, session)
        if permitted is None or permitted.id != current_app_user.id:
            raise HTTPException(
                403, "Payment-only acceptance is unavailable or expired"
            )
        session.refresh(order)
        if order.app_user_id != current_app_user.id or order.provider != "paypal":
            raise HTTPException(404, "Payment order not found")
        _require_resumable_acceptance_order(session, order)
        validate_order(order, data)
        return AppOrderPublic.model_validate(order)
    except PayPalError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    finally:
        client.close()


@router.post("/orders/{order_id}/replacement", response_model=AppOrderPublic)
def create_replacement_order(
    order_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    current_app_user: CurrentAppUser,
    idempotency_key: Annotated[str, Header(min_length=10, max_length=120)],
) -> AppOrderPublic:
    """Consume exactly one reviewed grant. No capture or implicit slot reset."""
    permitted = payment_only_user(request, session, verify_profile=True)
    if permitted is None or permitted.id != current_app_user.id:
        raise HTTPException(403, "Payment-only acceptance is unavailable")
    from app.api.routes.app_video_tasks import POC_BUDGET_LOCK_ID

    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(:id)"), {"id": POC_BUDGET_LOCK_ID}
    )
    client = get_paypal_client()
    try:

        def may_create() -> bool:
            user = payment_only_user(request, session)
            return user is not None and user.id == current_app_user.id

        order, submit = reserve_replacement(
            session, order_id, current_app_user.id, idempotency_key, client, may_create
        )
        if submit:
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
                raise PayPalError("Conflicting replacement provider reference", 409)
            order.provider_order_id = provider_id
            session.add(order)
            session.commit()
            session.refresh(order)
        return AppOrderPublic.model_validate(order)
    except PayPalError as exc:
        session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    finally:
        client.close()


@router.get("/orders/{order_id}/recovery", response_model=AppPayPalOrderRecoveryPublic)
def inspect_paypal_order_recovery(
    order_id: uuid.UUID,
    request: Request,
    response: Response,
    session: SessionDep,
    current_app_user: CurrentAppUser,
) -> AppPayPalOrderRecoveryPublic:
    """Owner-only read access survives expiry; it never grants checkout access."""
    response.headers["Cache-Control"] = "no-store"
    owner_id = current_app_user.id
    if (
        not settings.APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED
        or settings.ENVIRONMENT != "production"
        or settings.APP_AUTH_MODE != "clerk"
        or settings.PAYPAL_ENVIRONMENT != "live"
        or owner_id != settings.APP_PAYMENT_ONLY_ACCEPTANCE_USER_ID
    ):
        raise HTTPException(404, "Payment order not found")
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
    if not paypal_configured():
        return AppPayPalOrderRecoveryPublic(
            order_id=order_id,
            checked_at=datetime.now(UTC),
            reason_code="payment_service_unavailable",
        )
    verified = payment_only_user(request, session, verify_profile=True)
    profile_authorized = verified is not None and verified.id == owner_id
    client = None
    try:
        client = get_paypal_client()

        def may_resume() -> bool:
            permitted = payment_only_user(request, session)
            return (
                profile_authorized
                and permitted is not None
                and permitted.id == owner_id
            )

        return inspect_original_order(
            session,
            order_id=order_id,
            owner_id=owner_id,
            client=client,
            resume_authorized=may_resume,
        )
    except PayPalError:
        return AppPayPalOrderRecoveryPublic(
            order_id=order_id,
            checked_at=datetime.now(UTC),
            reason_code="provider_query_unconfirmed",
        )
    finally:
        if client is not None:
            client.close()


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
