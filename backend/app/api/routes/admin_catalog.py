import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, SQLModel, col, select
from starlette.concurrency import run_in_threadpool

from app import crud
from app.api.deps import (
    SessionDep,
    get_current_active_superuser,
    require_cloudflare_access,
)
from app.core.config import settings
from app.models import (
    AppEffect,
    AppEffectCategory,
    AppEffectRecommendation,
    AppEffectVariant,
    AppManagedMediaAsset,
    AppUser,
    AppVideoTask,
    Message,
    User,
)
from app.services.coin_wallet import CoinBalanceError, adjust_coin_balance
from app.services.effect_validation import (
    SUPPORTED_EFFECT_MODELS,
    validate_effect_variant,
)
from app.services.storage import ImageStorageError, get_image_storage

router = APIRouter(
    prefix="/admin/app",
    tags=["admin effect catalog"],
    dependencies=[
        Depends(require_cloudflare_access),
        Depends(get_current_active_superuser),
    ],
)

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AdminCategoryInput(SQLModel):
    slug: str = Field(min_length=1, max_length=80)
    name_zh: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    tones: list[str] = Field(min_length=3, max_length=3)
    sort_order: int = 0
    is_enabled: bool = True


class AdminCategoryPublic(AdminCategoryInput):
    id: uuid.UUID
    effect_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminCategoriesPublic(SQLModel):
    data: list[AdminCategoryPublic]
    count: int


class AdminVariantInput(SQLModel):
    duration_seconds: int = Field(ge=1, le=60)
    coin_cost: int = Field(ge=0)
    provider: str = "replicate"
    model: str
    model_type: str
    prompt: str = Field(min_length=1)
    negative_prompt: str | None = None
    prompt_version: str = "v1"
    is_default: bool = False
    is_enabled: bool = True


class AdminVariantPublic(AdminVariantInput):
    id: uuid.UUID


class AdminEffectInput(SQLModel):
    category_id: uuid.UUID
    slug: str = Field(min_length=1, max_length=120)
    title_zh: str = Field(min_length=1, max_length=160)
    title_en: str = Field(min_length=1, max_length=160)
    description: str | None = None
    input_image_count: int = Field(ge=1, le=2)
    poster_asset_id: uuid.UUID | None = None
    preview_asset_id: uuid.UUID | None = None
    sort_order: int = 0
    is_enabled: bool = True
    recommendation_label: str | None = Field(default=None, max_length=80)
    recommendation_ids: list[uuid.UUID] = Field(default_factory=list)


class AdminEffectPublic(AdminEffectInput):
    id: uuid.UUID
    publish_status: str
    variants: list[AdminVariantPublic] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminEffectsPublic(SQLModel):
    data: list[AdminEffectPublic]
    count: int


class AdminMediaPublic(SQLModel):
    id: uuid.UUID
    kind: str
    content_type: str
    size_bytes: int
    status: str
    url: str | None = None
    created_at: datetime | None = None


class AdminCoinAdjustmentInput(SQLModel):
    app_user_id: uuid.UUID
    delta: int
    reason: str = Field(min_length=2, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=255)


class AdminCoinAdjustmentPublic(SQLModel):
    balance: int
    ledger_id: uuid.UUID
    applied: bool


def _validated_slug(value: str) -> str:
    slug = value.strip().lower()
    if not SLUG_PATTERN.fullmatch(slug):
        raise HTTPException(
            status_code=422,
            detail="Slug must contain lowercase letters, numbers, and single hyphens",
        )
    return slug


def _serialize_category(
    session: SessionDep, category: AppEffectCategory
) -> AdminCategoryPublic:
    effect_count = session.exec(
        select(func.count())
        .select_from(AppEffect)
        .where(
            AppEffect.category_id == category.id,
            AppEffect.publish_status != "archived",
        )
    ).one()
    try:
        tones = json.loads(category.tones_json)
    except json.JSONDecodeError:
        tones = ["#476b70", "#18262c", "#98d9de"]
    return AdminCategoryPublic(
        id=category.id,
        slug=category.slug,
        name_zh=category.name_zh,
        name_en=category.name_en,
        tones=tones,
        sort_order=category.sort_order,
        is_enabled=category.is_enabled,
        effect_count=int(effect_count),
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _recommendation_ids(session: SessionDep, effect_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        session.exec(
            select(AppEffectRecommendation.recommended_effect_id)
            .where(AppEffectRecommendation.effect_id == effect_id)
            .order_by(col(AppEffectRecommendation.sort_order))
        ).all()
    )


def _serialize_effect(session: SessionDep, effect: AppEffect) -> AdminEffectPublic:
    variants = session.exec(
        select(AppEffectVariant)
        .where(AppEffectVariant.effect_id == effect.id)
        .order_by(col(AppEffectVariant.duration_seconds))
    ).all()
    return AdminEffectPublic(
        id=effect.id,
        category_id=effect.category_id,
        slug=effect.slug,
        title_zh=effect.title_zh,
        title_en=effect.title_en,
        description=effect.description,
        input_image_count=effect.input_image_count,
        poster_asset_id=effect.poster_asset_id,
        preview_asset_id=effect.preview_asset_id,
        sort_order=effect.sort_order,
        is_enabled=effect.is_enabled,
        recommendation_label=effect.recommendation_label,
        recommendation_ids=_recommendation_ids(session, effect.id),
        publish_status=effect.publish_status,
        variants=[AdminVariantPublic.model_validate(item) for item in variants],
        created_at=effect.created_at,
        updated_at=effect.updated_at,
    )


def _require_category(session: SessionDep, category_id: uuid.UUID) -> AppEffectCategory:
    category = session.get(AppEffectCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Effect category not found")
    return category


def _require_effect(session: SessionDep, effect_id: uuid.UUID) -> AppEffect:
    effect = session.get(AppEffect, effect_id)
    if effect is None:
        raise HTTPException(status_code=404, detail="Effect not found")
    return effect


def _validate_asset(
    session: SessionDep, asset_id: uuid.UUID | None, expected_kind: str
) -> None:
    if asset_id is None:
        return
    asset = session.get(AppManagedMediaAsset, asset_id)
    if asset is None or asset.status != "active" or asset.kind != expected_kind:
        raise HTTPException(status_code=422, detail=f"Invalid {expected_kind} asset")


def _replace_recommendations(
    *, session: SessionDep, effect: AppEffect, recommendation_ids: list[uuid.UUID]
) -> None:
    existing = session.exec(
        select(AppEffectRecommendation).where(
            AppEffectRecommendation.effect_id == effect.id
        )
    ).all()
    for item in existing:
        session.delete(item)
    for index, recommended_id in enumerate(dict.fromkeys(recommendation_ids), 1):
        if recommended_id == effect.id:
            raise HTTPException(
                status_code=422, detail="Effect cannot recommend itself"
            )
        recommended = session.get(AppEffect, recommended_id)
        if recommended is None or recommended.publish_status == "archived":
            raise HTTPException(status_code=422, detail="Recommended effect not found")
        session.add(
            AppEffectRecommendation(
                effect_id=effect.id,
                recommended_effect_id=recommended_id,
                sort_order=index * 10,
            )
        )


def _log(
    *,
    session: SessionDep,
    admin: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    summary: str,
) -> None:
    crud.create_app_admin_operation_log(
        session=session,
        admin_user=admin,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
    )


@router.get("/effect-categories", response_model=AdminCategoriesPublic)
def list_categories(session: SessionDep) -> AdminCategoriesPublic:
    categories = session.exec(
        select(AppEffectCategory).order_by(
            col(AppEffectCategory.sort_order), col(AppEffectCategory.created_at)
        )
    ).all()
    return AdminCategoriesPublic(
        data=[_serialize_category(session, item) for item in categories],
        count=len(categories),
    )


@router.post("/effect-categories", response_model=AdminCategoryPublic)
def create_category(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    body: AdminCategoryInput,
) -> AdminCategoryPublic:
    slug = _validated_slug(body.slug)
    if session.exec(
        select(AppEffectCategory).where(AppEffectCategory.slug == slug)
    ).first():
        raise HTTPException(status_code=409, detail="Category slug already exists")
    category = AppEffectCategory(
        slug=slug,
        name_zh=body.name_zh.strip(),
        name_en=body.name_en.strip(),
        tones_json=json.dumps(body.tones),
        sort_order=body.sort_order,
        is_enabled=body.is_enabled,
        created_by=current_admin.id,
        updated_by=current_admin.id,
    )
    session.add(category)
    session.flush()
    for index in range(1, 4):
        session.add(
            AppEffect(
                category_id=category.id,
                slug=f"{slug}-{index}",
                title_zh=f"新效果 {index}",
                title_en=f"NEW MOTION {index:02d}",
                input_image_count=2 if slug in {"kiss", "romance"} else 1,
                sort_order=index * 10,
                publish_status="draft",
                is_enabled=True,
                created_by=current_admin.id,
                updated_by=current_admin.id,
            )
        )
    session.commit()
    session.refresh(category)
    _log(
        session=session,
        admin=current_admin,
        action="effect_category.create",
        target_type="effect_category",
        target_id=category.id,
        summary=f"Created category {category.slug} with three draft effects",
    )
    return _serialize_category(session, category)


@router.put("/effect-categories/{category_id}", response_model=AdminCategoryPublic)
def update_category(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    category_id: uuid.UUID,
    body: AdminCategoryInput,
) -> AdminCategoryPublic:
    category = _require_category(session, category_id)
    slug = _validated_slug(body.slug)
    duplicate = session.exec(
        select(AppEffectCategory).where(
            AppEffectCategory.slug == slug, AppEffectCategory.id != category.id
        )
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Category slug already exists")
    category.slug = slug
    category.name_zh = body.name_zh.strip()
    category.name_en = body.name_en.strip()
    category.tones_json = json.dumps(body.tones)
    category.sort_order = body.sort_order
    category.is_enabled = body.is_enabled
    category.updated_by = current_admin.id
    category.updated_at = datetime.now(UTC)
    session.add(category)
    session.commit()
    session.refresh(category)
    _log(
        session=session,
        admin=current_admin,
        action="effect_category.update",
        target_type="effect_category",
        target_id=category.id,
        summary=f"Updated category {category.slug}",
    )
    return _serialize_category(session, category)


@router.delete("/effect-categories/{category_id}", response_model=Message)
def delete_category(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    category_id: uuid.UUID,
) -> Message:
    category = _require_category(session, category_id)
    effects = session.exec(
        select(AppEffect).where(AppEffect.category_id == category.id)
    ).all()
    effect_ids = [effect.id for effect in effects]
    task_count = 0
    if effect_ids:
        task_count = int(
            session.exec(
                select(func.count())
                .select_from(AppVideoTask)
                .where(col(AppVideoTask.effect_id).in_(effect_ids))
            ).one()
        )
    if task_count or any(effect.publish_status == "published" for effect in effects):
        now = datetime.now(UTC)
        category.is_enabled = False
        category.updated_at = now
        category.updated_by = current_admin.id
        session.add(category)
        for effect in effects:
            effect.publish_status = "archived"
            effect.is_enabled = False
            effect.updated_at = now
            effect.updated_by = current_admin.id
            session.add(effect)
        message = "Category archived"
    else:
        if effect_ids:
            recommendations = session.exec(
                select(AppEffectRecommendation).where(
                    or_(
                        col(AppEffectRecommendation.effect_id).in_(effect_ids),
                        col(AppEffectRecommendation.recommended_effect_id).in_(
                            effect_ids
                        ),
                    )
                )
            ).all()
            for recommendation in recommendations:
                session.delete(recommendation)
            variants = session.exec(
                select(AppEffectVariant).where(
                    col(AppEffectVariant.effect_id).in_(effect_ids)
                )
            ).all()
            for variant in variants:
                session.delete(variant)
            for effect in effects:
                session.delete(effect)
            session.flush()
        session.delete(category)
        message = "Draft category deleted"
    session.commit()
    _log(
        session=session,
        admin=current_admin,
        action="effect_category.delete",
        target_type="effect_category",
        target_id=category_id,
        summary=message,
    )
    return Message(message=message)


@router.get("/effects", response_model=AdminEffectsPublic)
def list_effects(
    session: SessionDep, category_id: uuid.UUID | None = None
) -> AdminEffectsPublic:
    statement = select(AppEffect)
    if category_id:
        statement = statement.where(AppEffect.category_id == category_id)
    effects = session.exec(
        statement.order_by(col(AppEffect.category_id), col(AppEffect.sort_order))
    ).all()
    return AdminEffectsPublic(
        data=[_serialize_effect(session, item) for item in effects],
        count=len(effects),
    )


@router.get("/effects/{effect_id}", response_model=AdminEffectPublic)
def read_effect(session: SessionDep, effect_id: uuid.UUID) -> AdminEffectPublic:
    return _serialize_effect(session, _require_effect(session, effect_id))


@router.post("/effects", response_model=AdminEffectPublic)
def create_effect(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    body: AdminEffectInput,
) -> AdminEffectPublic:
    _require_category(session, body.category_id)
    slug = _validated_slug(body.slug)
    if session.exec(select(AppEffect).where(AppEffect.slug == slug)).first():
        raise HTTPException(status_code=409, detail="Effect slug already exists")
    _validate_asset(session, body.poster_asset_id, "poster")
    _validate_asset(session, body.preview_asset_id, "preview_video")
    effect = AppEffect(
        **body.model_dump(exclude={"slug", "recommendation_ids"}),
        slug=slug,
        publish_status="draft",
        created_by=current_admin.id,
        updated_by=current_admin.id,
    )
    session.add(effect)
    session.flush()
    _replace_recommendations(
        session=session, effect=effect, recommendation_ids=body.recommendation_ids
    )
    session.commit()
    session.refresh(effect)
    _log(
        session=session,
        admin=current_admin,
        action="effect.create",
        target_type="effect",
        target_id=effect.id,
        summary=f"Created draft effect {effect.slug}",
    )
    return _serialize_effect(session, effect)


@router.put("/effects/{effect_id}", response_model=AdminEffectPublic)
def update_effect(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    effect_id: uuid.UUID,
    body: AdminEffectInput,
) -> AdminEffectPublic:
    effect = _require_effect(session, effect_id)
    _require_category(session, body.category_id)
    slug = _validated_slug(body.slug)
    duplicate = session.exec(
        select(AppEffect).where(AppEffect.slug == slug, AppEffect.id != effect.id)
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Effect slug already exists")
    _validate_asset(session, body.poster_asset_id, "poster")
    _validate_asset(session, body.preview_asset_id, "preview_video")
    effect.sqlmodel_update(
        body.model_dump(exclude={"recommendation_ids"}),
        update={
            "slug": slug,
            "updated_by": current_admin.id,
            "updated_at": datetime.now(UTC),
        },
    )
    _replace_recommendations(
        session=session, effect=effect, recommendation_ids=body.recommendation_ids
    )
    session.add(effect)
    session.commit()
    session.refresh(effect)
    _log(
        session=session,
        admin=current_admin,
        action="effect.update",
        target_type="effect",
        target_id=effect.id,
        summary=f"Updated effect {effect.slug}",
    )
    return _serialize_effect(session, effect)


@router.post("/effects/{effect_id}/variants", response_model=AdminVariantPublic)
def create_variant(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    effect_id: uuid.UUID,
    body: AdminVariantInput,
) -> AdminVariantPublic:
    effect = _require_effect(session, effect_id)
    if body.model not in SUPPORTED_EFFECT_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported effect model")
    variant = AppEffectVariant(effect_id=effect.id, **body.model_dump())
    session.add(variant)
    try:
        session.commit()
        session.refresh(variant)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Duration already exists") from exc
    _log(
        session=session,
        admin=current_admin,
        action="effect_variant.create",
        target_type="effect_variant",
        target_id=variant.id,
        summary=f"Added {variant.duration_seconds}s variant to {effect.slug}",
    )
    return AdminVariantPublic.model_validate(variant)


@router.put(
    "/effects/{effect_id}/variants/{variant_id}", response_model=AdminVariantPublic
)
def update_variant(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    effect_id: uuid.UUID,
    variant_id: uuid.UUID,
    body: AdminVariantInput,
) -> AdminVariantPublic:
    _require_effect(session, effect_id)
    variant = session.get(AppEffectVariant, variant_id)
    if variant is None or variant.effect_id != effect_id:
        raise HTTPException(status_code=404, detail="Effect variant not found")
    if body.model not in SUPPORTED_EFFECT_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported effect model")
    variant.sqlmodel_update(body.model_dump(), update={"updated_at": datetime.now(UTC)})
    session.add(variant)
    try:
        session.commit()
        session.refresh(variant)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Duration already exists") from exc
    _log(
        session=session,
        admin=current_admin,
        action="effect_variant.update",
        target_type="effect_variant",
        target_id=variant.id,
        summary=f"Updated {variant.duration_seconds}s variant",
    )
    return AdminVariantPublic.model_validate(variant)


@router.delete("/effects/{effect_id}/variants/{variant_id}", response_model=Message)
def delete_variant(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    effect_id: uuid.UUID,
    variant_id: uuid.UUID,
) -> Message:
    _require_effect(session, effect_id)
    variant = session.get(AppEffectVariant, variant_id)
    if variant is None or variant.effect_id != effect_id:
        raise HTTPException(status_code=404, detail="Effect variant not found")
    session.delete(variant)
    session.commit()
    _log(
        session=session,
        admin=current_admin,
        action="effect_variant.delete",
        target_type="effect_variant",
        target_id=variant_id,
        summary="Deleted effect variant",
    )
    return Message(message="Effect variant deleted")


@router.post("/effects/{effect_id}/publish", response_model=AdminEffectPublic)
def publish_effect(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    effect_id: uuid.UUID,
) -> AdminEffectPublic:
    effect = _require_effect(session, effect_id)
    category = _require_category(session, effect.category_id)
    if not category.is_enabled or not effect.is_enabled:
        raise HTTPException(
            status_code=422, detail="Category and effect must be enabled"
        )
    variants = session.exec(
        select(AppEffectVariant).where(
            AppEffectVariant.effect_id == effect.id,
            col(AppEffectVariant.is_enabled).is_(True),
        )
    ).all()
    if not variants:
        raise HTTPException(
            status_code=422, detail="At least one enabled variant is required"
        )
    for variant in variants:
        try:
            validate_effect_variant(
                provider=variant.provider,
                model=variant.model,
                input_image_count=effect.input_image_count,
                duration_seconds=variant.duration_seconds,
                prompt=variant.prompt,
                negative_prompt=variant.negative_prompt,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{variant.duration_seconds}s variant: {exc}",
            ) from exc
    effect.publish_status = "published"
    effect.published_at = datetime.now(UTC)
    effect.updated_by = current_admin.id
    effect.updated_at = datetime.now(UTC)
    session.add(effect)
    session.commit()
    session.refresh(effect)
    _log(
        session=session,
        admin=current_admin,
        action="effect.publish",
        target_type="effect",
        target_id=effect.id,
        summary=f"Published effect {effect.slug}",
    )
    return _serialize_effect(session, effect)


@router.delete("/effects/{effect_id}", response_model=Message)
def delete_effect(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    effect_id: uuid.UUID,
) -> Message:
    effect = _require_effect(session, effect_id)
    task_count = session.exec(
        select(func.count())
        .select_from(AppVideoTask)
        .where(AppVideoTask.effect_id == effect.id)
    ).one()
    if task_count or effect.publish_status == "published":
        effect.publish_status = "archived"
        effect.is_enabled = False
        effect.updated_at = datetime.now(UTC)
        session.add(effect)
        message = "Effect archived"
    else:
        session.delete(effect)
        message = "Draft effect deleted"
    session.commit()
    _log(
        session=session,
        admin=current_admin,
        action="effect.delete",
        target_type="effect",
        target_id=effect_id,
        summary=message,
    )
    return Message(message=message)


@router.post("/media-assets", response_model=AdminMediaPublic)
async def upload_media_asset(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> AdminMediaPublic:
    if kind not in {"poster", "preview_video"}:
        raise HTTPException(status_code=422, detail="Unsupported media kind")
    limit = (
        settings.MAX_CATALOG_IMAGE_BYTES
        if kind == "poster"
        else settings.MAX_CATALOG_VIDEO_BYTES
    )
    content = await file.read(limit + 1)
    try:
        stored = await run_in_threadpool(
            get_image_storage().store_managed_asset,
            kind=kind,
            content=content,
            uploaded_content_type=file.content_type,
        )
    except ImageStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    asset = AppManagedMediaAsset(
        kind=kind,
        object_key=stored.object_key,
        content_type=stored.content_type,
        size_bytes=stored.size,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        uploaded_by=current_admin.id,
    )
    try:
        session.add(asset)
        session.commit()
        session.refresh(asset)
    except SQLAlchemyError:
        session.rollback()
        await run_in_threadpool(get_image_storage().delete_object, stored.object_key)
        raise HTTPException(status_code=500, detail="Unable to record media asset")
    _log(
        session=session,
        admin=current_admin,
        action="media_asset.upload",
        target_type="media_asset",
        target_id=asset.id,
        summary=f"Uploaded {kind}",
    )
    try:
        url = get_image_storage().create_object_read_url(
            asset.object_key, expires_in=300
        )
    except ImageStorageError:
        url = None
    return AdminMediaPublic(
        id=asset.id,
        kind=asset.kind,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        status=asset.status,
        url=url,
        created_at=asset.created_at,
    )


@router.delete("/media-assets/{asset_id}", response_model=Message)
async def delete_media_asset(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    asset_id: uuid.UUID,
) -> Message:
    asset = session.get(AppManagedMediaAsset, asset_id)
    if asset is None or asset.status == "deleted":
        raise HTTPException(status_code=404, detail="Media asset not found")
    reference_count = session.exec(
        select(func.count())
        .select_from(AppEffect)
        .where(
            (AppEffect.poster_asset_id == asset.id)
            | (AppEffect.preview_asset_id == asset.id)
        )
    ).one()
    if reference_count:
        raise HTTPException(status_code=409, detail="Media asset is still in use")
    try:
        await run_in_threadpool(get_image_storage().delete_object, asset.object_key)
    except ImageStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    asset.status = "deleted"
    asset.deleted_at = datetime.now(UTC)
    asset.updated_at = datetime.now(UTC)
    session.add(asset)
    session.commit()
    _log(
        session=session,
        admin=current_admin,
        action="media_asset.delete",
        target_type="media_asset",
        target_id=asset.id,
        summary=f"Deleted {asset.kind}",
    )
    return Message(message="Media asset deleted")


@router.post("/coin-adjustments", response_model=AdminCoinAdjustmentPublic)
def adjust_user_coins(
    *,
    session: SessionDep,
    current_admin: User = Depends(get_current_active_superuser),
    body: AdminCoinAdjustmentInput,
) -> AdminCoinAdjustmentPublic:
    if body.delta == 0:
        raise HTTPException(status_code=422, detail="Coin adjustment must not be zero")
    if session.get(AppUser, body.app_user_id) is None:
        raise HTTPException(status_code=404, detail="App user not found")
    try:
        account, ledger, applied = adjust_coin_balance(
            session=session,
            app_user_id=body.app_user_id,
            delta=body.delta,
            entry_type="admin_adjustment",
            idempotency_key=body.idempotency_key.strip(),
            reason=body.reason.strip(),
            admin_user_id=current_admin.id,
        )
    except CoinBalanceError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    _log(
        session=session,
        admin=current_admin,
        action="coin.adjust",
        target_type="app_user",
        target_id=body.app_user_id,
        summary=f"Adjusted coin balance by {body.delta}",
    )
    return AdminCoinAdjustmentPublic(
        balance=account.balance, ledger_id=ledger.id, applied=applied
    )
