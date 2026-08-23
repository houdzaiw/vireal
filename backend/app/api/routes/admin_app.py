import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.api.deps import SessionDep, get_current_active_superuser
from app.api.routes.app_contents import serialize_app_content
from app.models import (
    AppAdminOperationLog,
    AppAdminOperationLogPublic,
    AppAdminOperationLogsPublic,
    AppConfigCreate,
    AppConfigPublic,
    AppConfigsPublic,
    AppConfigUpdate,
    AppContent,
    AppContentAdminPublic,
    AppContentsAdminPublic,
    AppOrderEventPublic,
    AppOrderEventsPublic,
    AppOrderPublic,
    AppOrdersPublic,
    AppUserAdminPublic,
    AppUsersPublic,
    AppUserStatusUpdate,
    Message,
    User,
)

router = APIRouter(
    prefix="/admin/app",
    tags=["admin app"],
    dependencies=[Depends(get_current_active_superuser)],
)


def serialize_admin_content(content: AppContent) -> AppContentAdminPublic:
    app_content = serialize_app_content(content)
    return AppContentAdminPublic(
        **app_content.model_dump(),
        status=content.status,
        deleted_at=content.deleted_at,
    )


def _normalize_config_create(config_in: AppConfigCreate) -> AppConfigCreate:
    key = config_in.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Config key cannot be empty")
    description = config_in.description.strip() if config_in.description else None
    return AppConfigCreate(
        key=key,
        value=config_in.value.strip(),
        description=description,
        is_enabled=config_in.is_enabled,
    )


def _normalize_config_update(config_in: AppConfigUpdate) -> AppConfigUpdate:
    config_data = config_in.model_dump(exclude_unset=True)
    if "key" in config_data and config_data["key"] is not None:
        config_data["key"] = config_data["key"].strip()
        if not config_data["key"]:
            raise HTTPException(status_code=400, detail="Config key cannot be empty")
    if "value" in config_data and config_data["value"] is not None:
        config_data["value"] = config_data["value"].strip()
    if "description" in config_data and config_data["description"] is not None:
        config_data["description"] = config_data["description"].strip() or None
    return AppConfigUpdate.model_validate(config_data)


def serialize_operation_log(log: AppAdminOperationLog) -> AppAdminOperationLogPublic:
    try:
        details = json.loads(log.details_json)
    except json.JSONDecodeError:
        details = {}
    return AppAdminOperationLogPublic(
        id=log.id,
        admin_user_id=log.admin_user_id,
        admin_email=log.admin_email,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        summary=log.summary,
        details=details,
        created_at=log.created_at,
    )


def log_admin_operation(
    *,
    session: SessionDep,
    current_admin: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    crud.create_app_admin_operation_log(
        session=session,
        admin_user=current_admin,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        details=details,
    )


@router.get("/users", response_model=AppUsersPublic)
def read_app_users(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    status: Literal["active", "disabled", "deleted"] | None = None,
) -> Any:
    """
    Retrieve App users for admin management.
    """
    app_users, count = crud.list_app_users_for_admin(
        session=session, skip=skip, limit=limit, status=status
    )
    return AppUsersPublic(
        data=[AppUserAdminPublic.model_validate(app_user) for app_user in app_users],
        count=count,
    )


@router.patch("/users/{app_user_id}/status", response_model=AppUserAdminPublic)
def update_app_user_status(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    app_user_id: uuid.UUID,
    status_in: AppUserStatusUpdate,
) -> Any:
    """
    Enable or disable an App user.
    """
    app_user = crud.get_app_user_for_admin(session=session, app_user_id=app_user_id)
    if not app_user:
        raise HTTPException(status_code=404, detail="App user not found")
    previous_status = app_user.status
    updated_user = crud.update_app_user_status(
        session=session, app_user=app_user, status=status_in.status
    )
    log_admin_operation(
        session=session,
        current_admin=current_admin,
        action="app_user.status_update",
        target_type="app_user",
        target_id=app_user_id,
        summary=f"Set App user status to {status_in.status}",
        details={
            "previous_status": previous_status,
            "new_status": status_in.status,
        },
    )
    return updated_user


@router.delete("/users/{app_user_id}", response_model=Message)
def delete_app_user(
    session: SessionDep,
    app_user_id: uuid.UUID,
    current_admin: User = Depends(get_current_active_superuser),
) -> Message:
    """
    Soft delete an App user.
    """
    app_user = crud.get_app_user_for_admin(session=session, app_user_id=app_user_id)
    if not app_user:
        raise HTTPException(status_code=404, detail="App user not found")
    previous_status = app_user.status
    crud.soft_delete_app_user(session=session, app_user=app_user)
    log_admin_operation(
        session=session,
        current_admin=current_admin,
        action="app_user.delete",
        target_type="app_user",
        target_id=app_user_id,
        summary="Soft deleted App user",
        details={
            "previous_status": previous_status,
            "nickname": app_user.nickname,
        },
    )
    return Message(message="App user deleted successfully")


@router.get("/contents", response_model=AppContentsAdminPublic)
def read_app_contents(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    status: Literal["active", "deleted"] | None = None,
) -> Any:
    """
    Retrieve App contents for admin management.
    """
    contents, count = crud.list_app_contents_for_admin(
        session=session, skip=skip, limit=limit, status=status
    )
    return AppContentsAdminPublic(
        data=[serialize_admin_content(content) for content in contents],
        count=count,
    )


@router.delete("/contents/{content_id}", response_model=Message)
def delete_app_content(
    session: SessionDep,
    content_id: uuid.UUID,
    current_admin: User = Depends(get_current_active_superuser),
) -> Message:
    """
    Soft delete an App content.
    """
    content = crud.get_app_content_for_admin(session=session, content_id=content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    previous_status = content.status
    crud.soft_delete_app_content(session=session, content=content)
    log_admin_operation(
        session=session,
        current_admin=current_admin,
        action="app_content.delete",
        target_type="app_content",
        target_id=content_id,
        summary="Soft deleted App content",
        details={
            "previous_status": previous_status,
            "app_user_id": str(content.app_user_id),
            "text_preview": (content.text or "")[:120],
        },
    )
    return Message(message="Content deleted successfully")


@router.get("/orders", response_model=AppOrdersPublic)
def read_app_orders(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    status: Literal["created", "paid", "failed", "refunded", "canceled"] | None = None,
    provider: Literal["apple", "google"] | None = None,
) -> Any:
    """
    Retrieve App payment orders for admin management.
    """
    orders, count = crud.list_app_orders_for_admin(
        session=session,
        skip=skip,
        limit=limit,
        status=status,
        provider=provider,
    )
    return AppOrdersPublic(
        data=[AppOrderPublic.model_validate(order) for order in orders],
        count=count,
    )


@router.get("/orders/{order_id}", response_model=AppOrderPublic)
def read_app_order(session: SessionDep, order_id: uuid.UUID) -> Any:
    """
    Get an App payment order by ID.
    """
    order = crud.get_app_order(session=session, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/orders/{order_id}/events", response_model=AppOrderEventsPublic)
def read_app_order_events(session: SessionDep, order_id: uuid.UUID) -> Any:
    """
    Retrieve callback events for an App payment order.
    """
    order = crud.get_app_order(session=session, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    events = crud.list_app_order_events(session=session, order_id=order_id)
    return AppOrderEventsPublic(
        data=[AppOrderEventPublic.model_validate(event) for event in events],
        count=len(events),
    )


@router.get("/operation-logs", response_model=AppAdminOperationLogsPublic)
def read_app_admin_operation_logs(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    action: str | None = None,
    target_type: str | None = None,
) -> Any:
    """
    Retrieve admin operation logs for App management actions.
    """
    logs, count = crud.list_app_admin_operation_logs(
        session=session,
        skip=skip,
        limit=limit,
        action=action,
        target_type=target_type,
    )
    return AppAdminOperationLogsPublic(
        data=[serialize_operation_log(log) for log in logs],
        count=count,
    )


@router.get("/configs", response_model=AppConfigsPublic)
def read_app_configs(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    is_enabled: bool | None = None,
) -> Any:
    """
    Retrieve App key-value configs for admin management.
    """
    configs, count = crud.list_app_configs_for_admin(
        session=session,
        skip=skip,
        limit=limit,
        is_enabled=is_enabled,
    )
    return AppConfigsPublic(
        data=[AppConfigPublic.model_validate(config) for config in configs],
        count=count,
    )


@router.post("/configs", response_model=AppConfigPublic)
def create_app_config(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    config_in: AppConfigCreate,
) -> Any:
    """
    Create an App key-value config.
    """
    normalized_config = _normalize_config_create(config_in)
    existing_config = crud.get_app_config_by_key(
        session=session, key=normalized_config.key
    )
    if existing_config:
        raise HTTPException(status_code=400, detail="Config key already exists")
    config = crud.create_app_config(session=session, config_in=normalized_config)
    log_admin_operation(
        session=session,
        current_admin=current_admin,
        action="app_config.create",
        target_type="app_config",
        target_id=config.id,
        summary=f"Created App config {config.key}",
        details={
            "key": config.key,
            "is_enabled": config.is_enabled,
        },
    )
    return config


@router.get("/configs/{config_id}", response_model=AppConfigPublic)
def read_app_config(session: SessionDep, config_id: uuid.UUID) -> Any:
    """
    Get an App key-value config by ID.
    """
    config = crud.get_app_config(session=session, config_id=config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return config


@router.patch("/configs/{config_id}", response_model=AppConfigPublic)
def update_app_config(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    config_id: uuid.UUID,
    config_in: AppConfigUpdate,
) -> Any:
    """
    Update an App key-value config.
    """
    config = crud.get_app_config(session=session, config_id=config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    normalized_config = _normalize_config_update(config_in)
    if normalized_config.key and normalized_config.key != config.key:
        existing_config = crud.get_app_config_by_key(
            session=session, key=normalized_config.key
        )
        if existing_config:
            raise HTTPException(status_code=400, detail="Config key already exists")
    previous_data = AppConfigPublic.model_validate(config).model_dump(mode="json")
    updated_config = crud.update_app_config(
        session=session,
        db_config=config,
        config_in=normalized_config,
    )
    log_admin_operation(
        session=session,
        current_admin=current_admin,
        action="app_config.update",
        target_type="app_config",
        target_id=config_id,
        summary=f"Updated App config {updated_config.key}",
        details={
            "previous": previous_data,
            "updated": AppConfigPublic.model_validate(updated_config).model_dump(
                mode="json"
            ),
        },
    )
    return updated_config
