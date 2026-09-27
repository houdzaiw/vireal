import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlmodel import Field, SQLModel, col, select

from app.api.deps import SessionDep
from app.core.config import settings
from app.models import (
    AppEffect,
    AppEffectCategory,
    AppEffectRecommendation,
    AppEffectVariant,
    AppManagedMediaAsset,
)
from app.services.storage import ImageStorageError, get_image_storage

router = APIRouter(prefix="/app", tags=["app effect catalog"])


class EffectVariantPublic(SQLModel):
    id: uuid.UUID
    duration_seconds: int
    coin_cost: int
    is_default: bool


class EffectPublic(SQLModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_slug: str
    slug: str
    title_zh: str
    title_en: str
    description: str | None = None
    input_image_count: int
    poster_url: str | None = None
    preview_video_url: str | None = None
    sort_order: int
    recommendation_label: str | None = None
    variants: list[EffectVariantPublic] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class EffectCategoryPublic(SQLModel):
    id: uuid.UUID
    slug: str
    name_zh: str
    name_en: str
    tones: list[str]
    sort_order: int
    effects: list[EffectPublic] = Field(default_factory=list)


class EffectCatalogPublic(SQLModel):
    categories: list[EffectCategoryPublic]


def _asset_url(session: SessionDep, asset_id: uuid.UUID | None) -> str | None:
    if asset_id is None:
        return None
    asset = session.get(AppManagedMediaAsset, asset_id)
    if asset is None or asset.status != "active":
        return None
    return f"{settings.API_V1_STR}/app/media-assets/{asset.id}"


def _variants_by_effect(session: SessionDep) -> dict[uuid.UUID, list[AppEffectVariant]]:
    variants = session.exec(
        select(AppEffectVariant)
        .where(col(AppEffectVariant.is_enabled).is_(True))
        .order_by(col(AppEffectVariant.duration_seconds))
    ).all()
    result: dict[uuid.UUID, list[AppEffectVariant]] = {}
    for variant in variants:
        result.setdefault(variant.effect_id, []).append(variant)
    return result


def _serialize_effect(
    *,
    session: SessionDep,
    effect: AppEffect,
    category: AppEffectCategory,
    variants: list[AppEffectVariant],
    recommendations: list[str] | None = None,
) -> EffectPublic:
    return EffectPublic(
        id=effect.id,
        category_id=category.id,
        category_slug=category.slug,
        slug=effect.slug,
        title_zh=effect.title_zh,
        title_en=effect.title_en,
        description=effect.description,
        input_image_count=effect.input_image_count,
        poster_url=_asset_url(session, effect.poster_asset_id),
        preview_video_url=_asset_url(session, effect.preview_asset_id),
        sort_order=effect.sort_order,
        recommendation_label=effect.recommendation_label,
        variants=[
            EffectVariantPublic(
                id=item.id,
                duration_seconds=item.duration_seconds,
                coin_cost=item.coin_cost,
                is_default=item.is_default,
            )
            for item in variants
        ],
        recommendations=recommendations or [],
    )


def _etag(payload: SQLModel) -> str:
    digest = hashlib.sha256(
        payload.model_dump_json(exclude_none=False).encode("utf-8")
    ).hexdigest()
    return f'"{digest}"'


@router.get("/effect-catalog", response_model=EffectCatalogPublic)
def read_effect_catalog(
    *, session: SessionDep, request: Request, response: Response
) -> Any:
    categories = session.exec(
        select(AppEffectCategory)
        .where(col(AppEffectCategory.is_enabled).is_(True))
        .order_by(col(AppEffectCategory.sort_order), col(AppEffectCategory.created_at))
    ).all()
    variants_by_effect = _variants_by_effect(session)
    public_categories: list[EffectCategoryPublic] = []
    for category in categories:
        effects = session.exec(
            select(AppEffect)
            .where(
                AppEffect.category_id == category.id,
                AppEffect.publish_status == "published",
                col(AppEffect.is_enabled).is_(True),
            )
            .order_by(col(AppEffect.sort_order), col(AppEffect.created_at))
        ).all()
        public_effects = [
            _serialize_effect(
                session=session,
                effect=effect,
                category=category,
                variants=variants_by_effect.get(effect.id, []),
            )
            for effect in effects
            if variants_by_effect.get(effect.id)
        ]
        if public_effects:
            try:
                tones = json.loads(category.tones_json)
            except json.JSONDecodeError:
                tones = ["#476b70", "#18262c", "#98d9de"]
            public_categories.append(
                EffectCategoryPublic(
                    id=category.id,
                    slug=category.slug,
                    name_zh=category.name_zh,
                    name_en=category.name_en,
                    tones=tones,
                    sort_order=category.sort_order,
                    effects=public_effects,
                )
            )
    payload = EffectCatalogPublic(categories=public_categories)
    current_etag = _etag(payload)
    if request.headers.get("if-none-match") == current_etag:
        return Response(status_code=304, headers={"ETag": current_etag})
    response.headers["ETag"] = current_etag
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return payload


@router.get("/media-assets/{asset_id}", response_model=None)
def read_media_asset(*, session: SessionDep, asset_id: uuid.UUID) -> RedirectResponse:
    asset = session.get(AppManagedMediaAsset, asset_id)
    if asset is None or asset.status != "active":
        raise HTTPException(status_code=404, detail="Media asset not found")
    try:
        url = get_image_storage().create_object_read_url(
            asset.object_key, expires_in=settings.R2_DOWNLOAD_URL_EXPIRE_SECONDS
        )
    except ImageStorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return RedirectResponse(
        url=url,
        status_code=307,
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/effects/{slug}", response_model=EffectPublic)
def read_effect(*, session: SessionDep, slug: str) -> EffectPublic:
    effect = session.exec(
        select(AppEffect).where(
            AppEffect.slug == slug,
            AppEffect.publish_status == "published",
            col(AppEffect.is_enabled).is_(True),
        )
    ).first()
    if effect is None:
        raise HTTPException(status_code=404, detail="Effect not found")
    category = session.get(AppEffectCategory, effect.category_id)
    if category is None or not category.is_enabled:
        raise HTTPException(status_code=404, detail="Effect not found")
    variants = _variants_by_effect(session).get(effect.id, [])
    if not variants:
        raise HTTPException(status_code=404, detail="Effect not found")
    recommendation_ids = session.exec(
        select(AppEffectRecommendation.recommended_effect_id)
        .where(AppEffectRecommendation.effect_id == effect.id)
        .order_by(col(AppEffectRecommendation.sort_order))
    ).all()
    recommendation_slugs = list(
        session.exec(
            select(AppEffect.slug).where(
                col(AppEffect.id).in_(recommendation_ids),
                AppEffect.publish_status == "published",
                col(AppEffect.is_enabled).is_(True),
            )
        ).all()
    )
    return _serialize_effect(
        session=session,
        effect=effect,
        category=category,
        variants=variants,
        recommendations=recommendation_slugs,
    )
