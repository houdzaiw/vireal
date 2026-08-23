import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, func, select

from app.core.security import get_password_hash, verify_password
from app.models import (
    AppAdminOperationLog,
    AppConfig,
    AppConfigCreate,
    AppConfigUpdate,
    AppContent,
    AppContentCreate,
    AppContentImage,
    AppDevice,
    AppOrder,
    AppOrderCreate,
    AppOrderEvent,
    AppUser,
    AppUserProfileUpdate,
    Item,
    ItemCreate,
    PaymentCallbackRequest,
    User,
    UserCreate,
    UserUpdate,
)


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


def create_item(*, session: Session, item_in: ItemCreate, owner_id: uuid.UUID) -> Item:
    db_item = Item.model_validate(item_in, update={"owner_id": owner_id})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


def hash_device_uuid(device_uuid: str) -> str:
    normalized_uuid = device_uuid.strip()
    return hashlib.sha256(normalized_uuid.encode("utf-8")).hexdigest()


def get_app_device_by_hash(
    *, session: Session, device_uuid_hash: str
) -> AppDevice | None:
    statement = select(AppDevice).where(AppDevice.device_uuid_hash == device_uuid_hash)
    return session.exec(statement).first()


def create_app_user_with_device(
    *, session: Session, device_uuid_hash: str, platform: str
) -> tuple[AppUser, AppDevice]:
    app_user = AppUser()
    session.add(app_user)
    session.flush()
    app_device = AppDevice(
        app_user_id=app_user.id,
        device_uuid_hash=device_uuid_hash,
        platform=platform,
    )
    session.add(app_device)
    session.commit()
    session.refresh(app_user)
    session.refresh(app_device)
    return app_user, app_device


def touch_app_device_login(*, session: Session, app_device: AppDevice) -> AppDevice:
    app_device.last_login_at = datetime.now(UTC)
    session.add(app_device)
    session.commit()
    session.refresh(app_device)
    return app_device


def update_app_user_profile(
    *, session: Session, app_user: AppUser, user_in: AppUserProfileUpdate
) -> AppUser:
    user_data = user_in.model_dump(exclude_unset=True)
    if "nickname" in user_data and user_data["nickname"] is not None:
        user_data["nickname"] = user_data["nickname"].strip()
    if "avatar_url" in user_data and user_data["avatar_url"] is not None:
        user_data["avatar_url"] = user_data["avatar_url"].strip()
    app_user.sqlmodel_update(user_data, update={"updated_at": datetime.now(UTC)})
    session.add(app_user)
    session.commit()
    session.refresh(app_user)
    return app_user


def create_app_content(
    *, session: Session, app_user: AppUser, content_in: AppContentCreate
) -> AppContent:
    text = content_in.text.strip() if content_in.text else None
    db_content = AppContent(app_user_id=app_user.id, text=text)
    session.add(db_content)
    session.flush()
    for index, image_url in enumerate(content_in.image_urls):
        session.add(
            AppContentImage(
                content_id=db_content.id,
                url=image_url.strip(),
                sort_order=index,
            )
        )
    session.commit()
    session.refresh(db_content)
    return db_content


def list_active_app_contents(
    *, session: Session, skip: int = 0, limit: int = 100
) -> tuple[list[AppContent], int]:
    base_filters = (
        AppContent.status == "active",
        col(AppContent.deleted_at).is_(None),
        AppUser.status == "active",
        col(AppUser.deleted_at).is_(None),
    )
    count_statement = (
        select(func.count())
        .select_from(AppContent)
        .join(AppUser)
        .where(*base_filters)
    )
    count = session.exec(count_statement).one()
    statement = (
        select(AppContent)
        .join(AppUser)
        .where(*base_filters)
        .order_by(col(AppContent.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    contents = list(session.exec(statement).all())
    return contents, count


def get_active_app_content(
    *, session: Session, content_id: uuid.UUID
) -> AppContent | None:
    statement = (
        select(AppContent)
        .join(AppUser)
        .where(
            AppContent.id == content_id,
            AppContent.status == "active",
            col(AppContent.deleted_at).is_(None),
            AppUser.status == "active",
            col(AppUser.deleted_at).is_(None),
        )
    )
    return session.exec(statement).first()


def list_app_users_for_admin(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
) -> tuple[list[AppUser], int]:
    filters: list[Any] = []
    if status:
        filters.append(AppUser.status == status)
    else:
        filters.append(col(AppUser.deleted_at).is_(None))
    count_statement = select(func.count()).select_from(AppUser).where(*filters)
    count = session.exec(count_statement).one()
    statement = (
        select(AppUser)
        .where(*filters)
        .order_by(col(AppUser.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    app_users = list(session.exec(statement).all())
    return app_users, count


def get_app_user_for_admin(
    *, session: Session, app_user_id: uuid.UUID
) -> AppUser | None:
    statement = select(AppUser).where(
        AppUser.id == app_user_id,
        col(AppUser.deleted_at).is_(None),
    )
    return session.exec(statement).first()


def update_app_user_status(
    *, session: Session, app_user: AppUser, status: str
) -> AppUser:
    app_user.status = status
    app_user.updated_at = datetime.now(UTC)
    session.add(app_user)
    session.commit()
    session.refresh(app_user)
    return app_user


def soft_delete_app_user(*, session: Session, app_user: AppUser) -> AppUser:
    now = datetime.now(UTC)
    app_user.status = "deleted"
    app_user.deleted_at = now
    app_user.updated_at = now
    session.add(app_user)
    session.commit()
    session.refresh(app_user)
    return app_user


def list_app_contents_for_admin(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
) -> tuple[list[AppContent], int]:
    filters: list[Any] = []
    if status:
        filters.append(AppContent.status == status)
    else:
        filters.append(col(AppContent.deleted_at).is_(None))
    count_statement = select(func.count()).select_from(AppContent).where(*filters)
    count = session.exec(count_statement).one()
    statement = (
        select(AppContent)
        .where(*filters)
        .order_by(col(AppContent.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    contents = list(session.exec(statement).all())
    return contents, count


def get_app_content_for_admin(
    *, session: Session, content_id: uuid.UUID
) -> AppContent | None:
    statement = select(AppContent).where(
        AppContent.id == content_id,
        col(AppContent.deleted_at).is_(None),
    )
    return session.exec(statement).first()


def soft_delete_app_content(
    *, session: Session, content: AppContent
) -> AppContent:
    now = datetime.now(UTC)
    content.status = "deleted"
    content.deleted_at = now
    content.updated_at = now
    session.add(content)
    session.commit()
    session.refresh(content)
    return content


def get_app_config(*, session: Session, config_id: uuid.UUID) -> AppConfig | None:
    return session.get(AppConfig, config_id)


def get_app_config_by_key(*, session: Session, key: str) -> AppConfig | None:
    statement = select(AppConfig).where(AppConfig.key == key)
    return session.exec(statement).first()


def create_app_config(
    *, session: Session, config_in: AppConfigCreate
) -> AppConfig:
    db_config = AppConfig.model_validate(config_in)
    session.add(db_config)
    session.commit()
    session.refresh(db_config)
    return db_config


def update_app_config(
    *, session: Session, db_config: AppConfig, config_in: AppConfigUpdate
) -> AppConfig:
    config_data = config_in.model_dump(exclude_unset=True)
    db_config.sqlmodel_update(config_data, update={"updated_at": datetime.now(UTC)})
    session.add(db_config)
    session.commit()
    session.refresh(db_config)
    return db_config


def list_app_configs_for_admin(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    is_enabled: bool | None = None,
) -> tuple[list[AppConfig], int]:
    filters: list[Any] = []
    if is_enabled is not None:
        filters.append(AppConfig.is_enabled == is_enabled)
    count_statement = select(func.count()).select_from(AppConfig).where(*filters)
    count = session.exec(count_statement).one()
    statement = (
        select(AppConfig)
        .where(*filters)
        .order_by(col(AppConfig.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    configs = list(session.exec(statement).all())
    return configs, count


def list_enabled_app_configs(*, session: Session) -> list[AppConfig]:
    statement = (
        select(AppConfig)
        .where(col(AppConfig.is_enabled).is_(True))
        .order_by(col(AppConfig.key).asc())
    )
    return list(session.exec(statement).all())


def create_app_admin_operation_log(
    *,
    session: Session,
    admin_user: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> AppAdminOperationLog:
    operation_log = AppAdminOperationLog(
        admin_user_id=admin_user.id,
        admin_email=admin_user.email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        details_json=json.dumps(details or {}, ensure_ascii=False, default=str),
    )
    session.add(operation_log)
    session.commit()
    session.refresh(operation_log)
    return operation_log


def list_app_admin_operation_logs(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    action: str | None = None,
    target_type: str | None = None,
) -> tuple[list[AppAdminOperationLog], int]:
    filters: list[Any] = []
    if action:
        filters.append(AppAdminOperationLog.action == action)
    if target_type:
        filters.append(AppAdminOperationLog.target_type == target_type)
    count_statement = (
        select(func.count()).select_from(AppAdminOperationLog).where(*filters)
    )
    count = session.exec(count_statement).one()
    statement = (
        select(AppAdminOperationLog)
        .where(*filters)
        .order_by(col(AppAdminOperationLog.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    logs = list(session.exec(statement).all())
    return logs, count


def create_app_order(
    *, session: Session, app_user: AppUser, order_in: AppOrderCreate
) -> AppOrder:
    currency = order_in.currency.upper() if order_in.currency else None
    db_order = AppOrder.model_validate(
        order_in,
        update={
            "app_user_id": app_user.id,
            "currency": currency,
        },
    )
    session.add(db_order)
    session.commit()
    session.refresh(db_order)
    return db_order


def get_app_order(*, session: Session, order_id: uuid.UUID) -> AppOrder | None:
    return session.get(AppOrder, order_id)


def get_app_order_for_app(
    *, session: Session, app_user: AppUser, order_id: uuid.UUID
) -> AppOrder | None:
    statement = select(AppOrder).where(
        AppOrder.id == order_id,
        AppOrder.app_user_id == app_user.id,
    )
    return session.exec(statement).first()


def list_app_orders_for_app(
    *,
    session: Session,
    app_user: AppUser,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[AppOrder], int]:
    count_statement = (
        select(func.count())
        .select_from(AppOrder)
        .where(AppOrder.app_user_id == app_user.id)
    )
    count = session.exec(count_statement).one()
    statement = (
        select(AppOrder)
        .where(AppOrder.app_user_id == app_user.id)
        .order_by(col(AppOrder.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    orders = list(session.exec(statement).all())
    return orders, count


def list_app_orders_for_admin(
    *,
    session: Session,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    provider: str | None = None,
) -> tuple[list[AppOrder], int]:
    filters: list[Any] = []
    if status:
        filters.append(AppOrder.status == status)
    if provider:
        filters.append(AppOrder.provider == provider)
    count_statement = select(func.count()).select_from(AppOrder).where(*filters)
    count = session.exec(count_statement).one()
    statement = (
        select(AppOrder)
        .where(*filters)
        .order_by(col(AppOrder.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    orders = list(session.exec(statement).all())
    return orders, count


def get_app_order_event_by_provider_event_id(
    *, session: Session, provider: str, event_id: str
) -> AppOrderEvent | None:
    statement = select(AppOrderEvent).where(
        AppOrderEvent.provider == provider,
        AppOrderEvent.event_id == event_id,
    )
    return session.exec(statement).first()


def list_app_order_events(
    *, session: Session, order_id: uuid.UUID
) -> list[AppOrderEvent]:
    statement = (
        select(AppOrderEvent)
        .where(AppOrderEvent.order_id == order_id)
        .order_by(col(AppOrderEvent.created_at).desc())
    )
    return list(session.exec(statement).all())


def process_payment_callback(
    *,
    session: Session,
    provider: str,
    callback: PaymentCallbackRequest,
) -> tuple[AppOrder | None, AppOrderEvent, bool]:
    existing_event = get_app_order_event_by_provider_event_id(
        session=session,
        provider=provider,
        event_id=callback.event_id,
    )
    if existing_event:
        order = (
            session.get(AppOrder, existing_event.order_id)
            if existing_event.order_id
            else None
        )
        return order, existing_event, True

    order = session.get(AppOrder, callback.order_id)
    now = datetime.now(UTC)
    raw_payload = json.dumps(callback.model_dump(mode="json"), ensure_ascii=False)
    event = AppOrderEvent(
        order_id=order.id if order else None,
        provider=provider,
        event_id=callback.event_id.strip(),
        event_type=callback.event_type.strip(),
        status=callback.status,
        transaction_id=callback.transaction_id.strip()
        if callback.transaction_id
        else None,
        raw_payload=raw_payload,
    )
    session.add(event)

    if order:
        order.status = callback.status
        order.updated_at = now
        if callback.transaction_id:
            order.transaction_id = callback.transaction_id.strip()
        if callback.status == "paid" and order.paid_at is None:
            order.paid_at = now
        session.add(order)

    session.commit()
    session.refresh(event)
    if order:
        session.refresh(order)
    return order, event, False
