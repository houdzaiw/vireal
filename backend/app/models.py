import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import EmailStr
from sqlalchemy import DateTime, Text
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class AppUserBase(SQLModel):
    nickname: str | None = Field(default=None, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=2048)
    status: str = Field(default="active", max_length=20, index=True)


class AppUser(AppUserBase, table=True):
    __tablename__ = "app_user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    devices: list[AppDevice] = Relationship(
        back_populates="app_user", cascade_delete=True
    )
    contents: list[AppContent] = Relationship(
        back_populates="app_user", cascade_delete=True
    )
    orders: list[AppOrder] = Relationship(
        back_populates="app_user", cascade_delete=True
    )
    generations: list[AppGeneration] = Relationship(
        back_populates="app_user", cascade_delete=True
    )


class AppDevice(SQLModel, table=True):
    __tablename__ = "app_device"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    app_user_id: uuid.UUID = Field(
        foreign_key="app_user.id", nullable=False, ondelete="CASCADE", index=True
    )
    device_uuid_hash: str = Field(unique=True, index=True, max_length=64)
    platform: str = Field(max_length=20)
    last_login_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    app_user: AppUser | None = Relationship(back_populates="devices")


class AppUserPublic(AppUserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class AppDeviceLoginRequest(SQLModel):
    device_uuid: str = Field(min_length=8, max_length=255)
    platform: Literal["ios", "android"]


class AppDeviceLoginResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    app_user: AppUserPublic
    is_new_user: bool


class AppTokenPayload(SQLModel):
    sub: str | None = None
    typ: str | None = None


class AppUserProfileUpdate(SQLModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=2048)


class AppUploadPublic(SQLModel):
    url: str
    content_type: str
    size: int


class AppContent(SQLModel, table=True):
    __tablename__ = "app_content"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    app_user_id: uuid.UUID = Field(
        foreign_key="app_user.id", nullable=False, ondelete="CASCADE", index=True
    )
    text: str | None = Field(default=None, max_length=2000)
    status: str = Field(default="active", max_length=20, index=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    app_user: AppUser | None = Relationship(back_populates="contents")
    images: list[AppContentImage] = Relationship(
        back_populates="content", cascade_delete=True
    )


class AppContentImage(SQLModel, table=True):
    __tablename__ = "app_content_image"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    content_id: uuid.UUID = Field(
        foreign_key="app_content.id", nullable=False, ondelete="CASCADE", index=True
    )
    url: str = Field(max_length=2048)
    sort_order: int = Field(default=0)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    content: AppContent | None = Relationship(back_populates="images")


class AppContentCreate(SQLModel):
    text: str | None = Field(default=None, max_length=2000)
    image_urls: list[str] = Field(default_factory=list)


class AppContentImagePublic(SQLModel):
    id: uuid.UUID
    url: str
    sort_order: int


class AppContentAuthorPublic(SQLModel):
    id: uuid.UUID
    nickname: str | None = None
    avatar_url: str | None = None


class AppContentPublic(SQLModel):
    id: uuid.UUID
    app_user_id: uuid.UUID
    author: AppContentAuthorPublic
    text: str | None = None
    images: list[AppContentImagePublic]
    created_at: datetime | None = None


class AppContentsPublic(SQLModel):
    data: list[AppContentPublic]
    count: int


class AppGeneration(SQLModel, table=True):
    __tablename__ = "app_generation"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    app_user_id: uuid.UUID = Field(
        foreign_key="app_user.id", nullable=False, ondelete="CASCADE", index=True
    )
    kind: str = Field(max_length=20, index=True)
    model: str = Field(max_length=80)
    provider: str = Field(default="local", max_length=40, index=True)
    provider_task_id: str | None = Field(default=None, max_length=200, index=True)
    status: str = Field(default="processing", max_length=20, index=True)
    prompt: str = Field(max_length=2000)
    style: str = Field(default="写实", max_length=50)
    aspect_ratio: str = Field(default="9:16", max_length=20)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    consistency: bool = Field(default=True)
    reference_image_url: str | None = Field(default=None, max_length=2048)
    character_image_url: str | None = Field(default=None, max_length=2048)
    output_url: str | None = Field(default=None, max_length=2048)
    error_message: str | None = Field(default=None, max_length=500)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        index=True,
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    app_user: AppUser | None = Relationship(back_populates="generations")


class AppGenerationCreate(SQLModel):
    kind: Literal["video", "image"]
    prompt: str = Field(min_length=1, max_length=2000)
    style: str = Field(default="写实", min_length=1, max_length=50)
    aspect_ratio: str = Field(default="9:16", min_length=1, max_length=20)
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    consistency: bool = True
    reference_image_url: str | None = Field(default=None, max_length=2048)
    character_image_url: str | None = Field(default=None, max_length=2048)


class AppGenerationPublic(SQLModel):
    id: uuid.UUID
    app_user_id: uuid.UUID
    kind: str
    model: str
    provider: str
    provider_task_id: str | None = None
    status: str
    prompt: str
    style: str
    aspect_ratio: str
    duration_seconds: int | None = None
    consistency: bool
    reference_image_url: str | None = None
    character_image_url: str | None = None
    output_url: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class AppGenerationsPublic(SQLModel):
    data: list[AppGenerationPublic]
    count: int


class AppGenerationQuotaPublic(SQLModel):
    video_total: int
    video_used: int
    video_remaining: int
    image_total: int
    image_used: int
    image_remaining: int


class AppGenerationAdminPublic(AppGenerationPublic):
    deleted_at: datetime | None = None


class AppGenerationsAdminPublic(SQLModel):
    data: list[AppGenerationAdminPublic]
    count: int


class AppUserAdminPublic(AppUserPublic):
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class AppUsersPublic(SQLModel):
    data: list[AppUserAdminPublic]
    count: int


class AppUserStatusUpdate(SQLModel):
    status: Literal["active", "disabled"]


class AppContentAdminPublic(AppContentPublic):
    status: str
    deleted_at: datetime | None = None


class AppContentsAdminPublic(SQLModel):
    data: list[AppContentAdminPublic]
    count: int


class AppConfigBase(SQLModel):
    key: str = Field(min_length=1, max_length=120, index=True)
    value: str = Field(max_length=5000)
    description: str | None = Field(default=None, max_length=255)
    is_enabled: bool = Field(default=True, index=True)


class AppConfig(AppConfigBase, table=True):
    __tablename__ = "app_config"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    key: str = Field(unique=True, index=True, min_length=1, max_length=120)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class AppConfigCreate(AppConfigBase):
    pass


class AppConfigUpdate(SQLModel):
    key: str | None = Field(default=None, min_length=1, max_length=120)
    value: str | None = Field(default=None, max_length=5000)
    description: str | None = Field(default=None, max_length=255)
    is_enabled: bool | None = None


class AppConfigPublic(AppConfigBase):
    id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AppConfigsPublic(SQLModel):
    data: list[AppConfigPublic]
    count: int


class AppConfigValuesPublic(SQLModel):
    data: dict[str, str]
    count: int


class AppOrder(SQLModel, table=True):
    __tablename__ = "app_order"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    app_user_id: uuid.UUID = Field(
        foreign_key="app_user.id", nullable=False, ondelete="CASCADE", index=True
    )
    provider: str = Field(max_length=20, index=True)
    product_id: str = Field(max_length=255)
    status: str = Field(default="created", max_length=20, index=True)
    amount: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    transaction_id: str | None = Field(default=None, max_length=255, index=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    paid_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    app_user: AppUser | None = Relationship(back_populates="orders")
    events: list[AppOrderEvent] = Relationship(
        back_populates="order", cascade_delete=True
    )


class AppOrderEvent(SQLModel, table=True):
    __tablename__ = "app_order_event"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="app_order.id",
        nullable=True,
        ondelete="SET NULL",
        index=True,
    )
    provider: str = Field(max_length=20, index=True)
    event_id: str = Field(max_length=255, index=True)
    event_type: str = Field(max_length=100)
    status: str = Field(max_length=20, index=True)
    transaction_id: str | None = Field(default=None, max_length=255)
    raw_payload: str = Field(sa_type=Text)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    order: AppOrder | None = Relationship(back_populates="events")


class AppOrderCreate(SQLModel):
    provider: Literal["apple", "google"]
    product_id: str = Field(min_length=1, max_length=255)
    amount: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class AppOrderPublic(SQLModel):
    id: uuid.UUID
    app_user_id: uuid.UUID
    provider: str
    product_id: str
    status: str
    amount: int | None = None
    currency: str | None = None
    transaction_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    paid_at: datetime | None = None


class AppOrdersPublic(SQLModel):
    data: list[AppOrderPublic]
    count: int


class PaymentCallbackRequest(SQLModel):
    order_id: uuid.UUID
    event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=100)
    status: Literal["paid", "failed", "refunded", "canceled"]
    transaction_id: str | None = Field(default=None, max_length=255)
    raw_data: dict[str, Any] = Field(default_factory=dict)


class AppOrderEventPublic(SQLModel):
    id: uuid.UUID
    order_id: uuid.UUID | None = None
    provider: str
    event_id: str
    event_type: str
    status: str
    transaction_id: str | None = None
    raw_payload: str
    created_at: datetime | None = None


class AppOrderEventsPublic(SQLModel):
    data: list[AppOrderEventPublic]
    count: int


class PaymentCallbackResponse(SQLModel):
    order: AppOrderPublic | None = None
    event: AppOrderEventPublic
    is_duplicate: bool
    message: str


class AppAdminOperationLog(SQLModel, table=True):
    __tablename__ = "app_admin_operation_log"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    admin_user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        ondelete="SET NULL",
        index=True,
    )
    admin_email: str = Field(max_length=255, index=True)
    action: str = Field(max_length=120, index=True)
    target_type: str = Field(max_length=80, index=True)
    target_id: uuid.UUID | None = Field(default=None, index=True)
    summary: str | None = Field(default=None, max_length=500)
    details_json: str = Field(default="{}", sa_type=Text)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        index=True,
    )


class AppAdminOperationLogPublic(SQLModel):
    id: uuid.UUID
    admin_user_id: uuid.UUID | None = None
    admin_email: str
    action: str
    target_type: str
    target_id: uuid.UUID | None = None
    summary: str | None = None
    details: dict[str, Any]
    created_at: datetime | None = None


class AppAdminOperationLogsPublic(SQLModel):
    data: list[AppAdminOperationLogPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
