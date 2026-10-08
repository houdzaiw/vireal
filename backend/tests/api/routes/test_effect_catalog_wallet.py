import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import (
    AppAdminOperationLog,
    AppEffect,
    AppEffectCategory,
    AppEffectVariant,
    AppManagedMediaAsset,
)
from tests.utils.app_user import app_authentication_headers


def _category_payload(slug: str) -> dict[str, object]:
    return {
        "slug": slug,
        "name_zh": "测试分类",
        "name_en": "TEST CATEGORY",
        "tones": ["#123456", "#234567", "#abcdef"],
        "sort_order": 999,
        "is_enabled": True,
    }


def _effect_payload(
    category_id: str,
    slug: str,
    *,
    input_image_count: int = 1,
    recommendation_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "category_id": category_id,
        "slug": slug,
        "title_zh": "测试效果",
        "title_en": "TEST EFFECT",
        "description": "Catalogue test effect",
        "input_image_count": input_image_count,
        "poster_asset_id": None,
        "preview_asset_id": None,
        "sort_order": 50,
        "is_enabled": True,
        "recommendation_label": "推荐",
        "recommendation_ids": recommendation_ids or [],
    }


def _variant_payload(
    *,
    duration: int = 5,
    model: str = "minimax/video-01",
    negative_prompt: str | None = "text, watermark",
) -> dict[str, object]:
    return {
        "duration_seconds": duration,
        "coin_cost": 12,
        "provider": "replicate",
        "model": model,
        "model_type": "image-to-video",
        "prompt": "A safe cinematic test motion",
        "negative_prompt": negative_prompt,
        "prompt_version": "v1",
        "is_default": True,
        "is_enabled": True,
    }


def test_admin_category_defaults_publish_validation_and_public_etag(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    slug = f"test-{uuid.uuid4().hex[:10]}"
    category_response = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(slug),
    )
    assert category_response.status_code == 200
    category = category_response.json()
    assert category["effect_count"] == 3

    effects_response = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category["id"]},
        headers=superuser_token_headers,
    )
    assert effects_response.status_code == 200
    effects = effects_response.json()["data"]
    assert len(effects) == 3
    effect = effects[0]

    invalid_publish = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/publish",
        headers=superuser_token_headers,
    )
    assert invalid_publish.status_code == 422

    unknown_model = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants",
        headers=superuser_token_headers,
        json={
            "duration_seconds": 5,
            "coin_cost": 12,
            "provider": "replicate",
            "model": "unknown/video-model",
            "model_type": "image-to-video",
            "prompt": "A safe test motion",
            "prompt_version": "v1",
            "is_default": True,
            "is_enabled": True,
        },
    )
    assert unknown_model.status_code == 422

    variant_response = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants",
        headers=superuser_token_headers,
        json={
            "duration_seconds": 5,
            "coin_cost": 12,
            "provider": "replicate",
            "model": "minimax/video-01",
            "model_type": "image-to-video",
            "prompt": "A safe cinematic test motion",
            "negative_prompt": "text, watermark",
            "prompt_version": "v1",
            "is_default": True,
            "is_enabled": True,
        },
    )
    assert variant_response.status_code == 200

    publish_response = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/publish",
        headers=superuser_token_headers,
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["publish_status"] == "published"

    catalog_response = client.get(f"{settings.API_V1_STR}/app/effect-catalog")
    assert catalog_response.status_code == 200
    etag = catalog_response.headers["etag"]
    category_public = next(
        item
        for item in catalog_response.json()["categories"]
        if item["id"] == category["id"]
    )
    assert len(category_public["effects"]) == 1
    public_effect = category_public["effects"][0]
    assert public_effect["poster_url"] is None
    assert public_effect["preview_video_url"] is None
    assert "prompt" not in public_effect
    assert "model" not in public_effect

    not_modified = client.get(
        f"{settings.API_V1_STR}/app/effect-catalog",
        headers={"If-None-Match": etag},
    )
    assert not_modified.status_code == 304


def test_duration_release_gate_filters_catalog_and_detail_without_deleting_config(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    superuser_token_headers: dict[str, str],
) -> None:
    category = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(f"duration-gate-{uuid.uuid4().hex[:8]}"),
    ).json()
    effects = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category["id"]},
        headers=superuser_token_headers,
    ).json()["data"]
    effect, longer_only = effects[:2]
    longer_ids = []
    for target, durations in ((effect, [5, 10, 15]), (longer_only, [15])):
        updated = client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{target['id']}",
            headers=superuser_token_headers,
            json=_effect_payload(category["id"], target["slug"]),
        )
        assert updated.status_code == 200
        for duration in durations:
            model = {
                5: "minimax/video-01",
                10: "wan-video/wan-2.7-r2v",
                15: "bytedance/seedance-2.0",
            }[duration]
            variant = client.post(
                f"{settings.API_V1_STR}/admin/app/effects/{target['id']}/variants",
                headers=superuser_token_headers,
                json=_variant_payload(
                    duration=duration, model=model, negative_prompt=None
                ),
            )
            assert variant.status_code == 200
            if duration == 15:
                longer_ids.append(uuid.UUID(variant.json()["id"]))
        assert (
            client.post(
                f"{settings.API_V1_STR}/admin/app/effects/{target['id']}/publish",
                headers=superuser_token_headers,
            ).status_code
            == 200
        )

    monkeypatch.setattr(settings, "APP_EFFECT_MAX_DURATION_SECONDS", 15)
    unrestricted = client.get(f"{settings.API_V1_STR}/app/effect-catalog")
    monkeypatch.setattr(settings, "APP_EFFECT_MAX_DURATION_SECONDS", 10)
    restricted = client.get(
        f"{settings.API_V1_STR}/app/effect-catalog",
        headers={"If-None-Match": unrestricted.headers["etag"]},
    )
    assert restricted.status_code == 200
    assert restricted.headers["etag"] != unrestricted.headers["etag"]
    public = next(
        c for c in restricted.json()["categories"] if c["id"] == category["id"]
    )
    assert [e["id"] for e in public["effects"]] == [effect["id"]]
    assert [v["duration_seconds"] for v in public["effects"][0]["variants"]] == [5, 10]
    detail = client.get(f"{settings.API_V1_STR}/app/effects/{effect['slug']}")
    assert [v["duration_seconds"] for v in detail.json()["variants"]] == [5, 10]
    assert (
        client.get(
            f"{settings.API_V1_STR}/app/effects/{longer_only['slug']}"
        ).status_code
        == 404
    )
    for variant_id in longer_ids:
        variant_config = db.get(AppEffectVariant, variant_id)
        assert variant_config is not None and variant_config.is_enabled
        assert variant_config.duration_seconds == 15
    monkeypatch.setattr(settings, "APP_EFFECT_MAX_DURATION_SECONDS", 15)
    restored = client.get(f"{settings.API_V1_STR}/app/effects/{effect['slug']}")
    assert [v["duration_seconds"] for v in restored.json()["variants"]] == [5, 10, 15]


def test_admin_coin_adjustment_is_idempotent_and_wallet_is_server_owned(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    app_headers, login = app_authentication_headers(client=client)
    app_user_id = str(login["app_user"]["id"])
    idempotency_key = f"admin-grant-{uuid.uuid4()}"
    payload = {
        "app_user_id": app_user_id,
        "delta": 25,
        "reason": "Automated wallet test grant",
        "idempotency_key": idempotency_key,
    }

    first = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=superuser_token_headers,
        json=payload,
    )
    duplicate = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=superuser_token_headers,
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["applied"] is True
    assert first.json()["balance"] == 25
    assert duplicate.status_code == 200
    assert duplicate.json()["applied"] is False
    assert duplicate.json()["balance"] == 25

    conflicting = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=superuser_token_headers,
        json={**payload, "delta": 30},
    )
    assert conflicting.status_code == 409

    overdraw = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=superuser_token_headers,
        json={
            **payload,
            "delta": -26,
            "idempotency_key": f"admin-debit-{uuid.uuid4()}",
        },
    )
    assert overdraw.status_code == 409

    wallet = client.get(
        f"{settings.API_V1_STR}/app/wallet",
        headers=app_headers,
    )
    assert wallet.status_code == 200
    data = wallet.json()
    assert data["balance"] == 25
    assert data["daily_remaining"] >= 0
    assert data["concurrent_remaining"] >= 0
    assert len(data["ledger"]) == 1


def test_admin_media_upload_validates_signature_and_records_asset(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    invalid = client.post(
        f"{settings.API_V1_STR}/admin/app/media-assets",
        headers=superuser_token_headers,
        data={"kind": "preview_video"},
        files={"file": ("preview.mp4", b"not-an-mp4", "video/mp4")},
    )
    assert invalid.status_code == 400

    uploaded = client.post(
        f"{settings.API_V1_STR}/admin/app/media-assets",
        headers=superuser_token_headers,
        data={"kind": "poster"},
        files={
            "file": (
                "poster.png",
                b"\x89PNG\r\n\x1a\nmanaged-media-test",
                "image/png",
            )
        },
    )
    assert uploaded.status_code == 200
    asset = uploaded.json()
    assert asset["kind"] == "poster"
    assert asset["status"] == "active"

    deleted = client.delete(
        f"{settings.API_V1_STR}/admin/app/media-assets/{asset['id']}",
        headers=superuser_token_headers,
    )
    assert deleted.status_code == 200


def test_admin_can_delete_an_unpublished_category_and_its_three_drafts(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    slug = f"delete-{uuid.uuid4().hex[:10]}"
    created = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(slug),
    )
    assert created.status_code == 200
    category_id = created.json()["id"]

    deleted = client.delete(
        f"{settings.API_V1_STR}/admin/app/effect-categories/{category_id}",
        headers=superuser_token_headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "Draft category deleted"

    effects = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category_id},
        headers=superuser_token_headers,
    )
    assert effects.status_code == 200
    assert effects.json()["count"] == 0


def test_admin_category_and_effect_crud_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    first_slug = f"crud-{uuid.uuid4().hex[:8]}"
    second_slug = f"crud-{uuid.uuid4().hex[:8]}"
    invalid = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload("Not Valid"),
    )
    assert invalid.status_code == 422

    first = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(first_slug),
    ).json()
    second = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(second_slug),
    ).json()
    duplicate = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(first_slug),
    )
    assert duplicate.status_code == 409

    duplicate_update = client.put(
        f"{settings.API_V1_STR}/admin/app/effect-categories/{first['id']}",
        headers=superuser_token_headers,
        json=_category_payload(second_slug),
    )
    assert duplicate_update.status_code == 409
    updated_slug = f"updated-{uuid.uuid4().hex[:8]}"
    updated = client.put(
        f"{settings.API_V1_STR}/admin/app/effect-categories/{first['id']}",
        headers=superuser_token_headers,
        json={**_category_payload(updated_slug), "name_zh": " 更新分类 "},
    )
    assert updated.status_code == 200
    assert updated.json()["slug"] == updated_slug
    assert updated.json()["name_zh"] == "更新分类"
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effect-categories/{uuid.uuid4()}",
            headers=superuser_token_headers,
            json=_category_payload(updated_slug),
        ).status_code
        == 404
    )

    category_record = db.get(AppEffectCategory, uuid.UUID(first["id"]))
    assert category_record is not None
    category_record.tones_json = "not-json"
    db.add(category_record)
    db.commit()
    categories = client.get(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
    ).json()["data"]
    serialized = next(item for item in categories if item["id"] == first["id"])
    assert serialized["tones"] == ["#476b70", "#18262c", "#98d9de"]

    defaults = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": first["id"]},
        headers=superuser_token_headers,
    ).json()["data"]
    assert len(defaults) == 3
    assert (
        client.get(
            f"{settings.API_V1_STR}/admin/app/effects/{uuid.uuid4()}",
            headers=superuser_token_headers,
        ).status_code
        == 404
    )

    effect_slug = f"effect-{uuid.uuid4().hex[:8]}"
    created = client.post(
        f"{settings.API_V1_STR}/admin/app/effects",
        headers=superuser_token_headers,
        json=_effect_payload(
            first["id"], effect_slug, recommendation_ids=[defaults[0]["id"]]
        ),
    )
    assert created.status_code == 200
    effect = created.json()
    assert effect["recommendation_ids"] == [defaults[0]["id"]]
    assert (
        client.post(
            f"{settings.API_V1_STR}/admin/app/effects",
            headers=superuser_token_headers,
            json=_effect_payload(first["id"], effect_slug),
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{settings.API_V1_STR}/admin/app/effects",
            headers=superuser_token_headers,
            json=_effect_payload(str(uuid.uuid4()), f"missing-{uuid.uuid4().hex[:8]}"),
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
            headers=superuser_token_headers,
            json=_effect_payload(first["id"], defaults[0]["slug"]),
        ).status_code
        == 409
    )
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
            headers=superuser_token_headers,
            json=_effect_payload(
                first["id"], effect_slug, recommendation_ids=[effect["id"]]
            ),
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
            headers=superuser_token_headers,
            json=_effect_payload(
                first["id"], effect_slug, recommendation_ids=[str(uuid.uuid4())]
            ),
        ).status_code
        == 422
    )
    invalid_asset_payload = {
        **_effect_payload(first["id"], effect_slug),
        "poster_asset_id": str(uuid.uuid4()),
    }
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
            headers=superuser_token_headers,
            json=invalid_asset_payload,
        ).status_code
        == 422
    )

    updated_effect = client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=superuser_token_headers,
        json={
            **_effect_payload(
                second["id"], effect_slug, recommendation_ids=[defaults[1]["id"]]
            ),
            "title_en": "UPDATED EFFECT",
        },
    )
    assert updated_effect.status_code == 200
    assert updated_effect.json()["category_id"] == second["id"]
    assert updated_effect.json()["title_en"] == "UPDATED EFFECT"
    assert (
        client.delete(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
            headers=superuser_token_headers,
        ).json()["message"]
        == "Draft effect deleted"
    )

    audit_actions = set(db.exec(select(AppAdminOperationLog.action)).all())
    assert {"effect_category.update", "effect.create", "effect.delete"}.issubset(
        audit_actions
    )


def test_admin_variant_lifecycle_and_publish_guards(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    slug = f"variants-{uuid.uuid4().hex[:8]}"
    category = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(slug),
    ).json()
    effects = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category["id"]},
        headers=superuser_token_headers,
    ).json()["data"]
    effect = effects[0]

    created = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants",
        headers=superuser_token_headers,
        json=_variant_payload(),
    )
    assert created.status_code == 200
    variant = created.json()
    duplicate = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants",
        headers=superuser_token_headers,
        json=_variant_payload(),
    )
    assert duplicate.status_code == 409
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants/{uuid.uuid4()}",
            headers=superuser_token_headers,
            json=_variant_payload(),
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants/{variant['id']}",
            headers=superuser_token_headers,
            json=_variant_payload(model="unknown/model"),
        ).status_code
        == 422
    )
    updated = client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants/{variant['id']}",
        headers=superuser_token_headers,
        json={**_variant_payload(), "coin_cost": 19},
    )
    assert updated.status_code == 200
    assert updated.json()["coin_cost"] == 19

    disabled_effect = client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=superuser_token_headers,
        json={**_effect_payload(category["id"], effect["slug"]), "is_enabled": False},
    )
    assert disabled_effect.status_code == 200
    assert (
        client.post(
            f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/publish",
            headers=superuser_token_headers,
        ).status_code
        == 422
    )
    client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=superuser_token_headers,
        json=_effect_payload(category["id"], effect["slug"]),
    )
    published = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/publish",
        headers=superuser_token_headers,
    )
    assert published.status_code == 200
    archived = client.delete(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=superuser_token_headers,
    )
    assert archived.json()["message"] == "Effect archived"

    other = effects[1]
    other_variant = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{other['id']}/variants",
        headers=superuser_token_headers,
        json=_variant_payload(
            duration=15,
            model="bytedance/seedance-2.0",
            negative_prompt="not-supported",
        ),
    ).json()
    invalid_publish = client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{other['id']}/publish",
        headers=superuser_token_headers,
    )
    assert invalid_publish.status_code == 422
    assert "negative prompt" in invalid_publish.json()["detail"]
    assert (
        client.delete(
            f"{settings.API_V1_STR}/admin/app/effects/{other['id']}/variants/{other_variant['id']}",
            headers=superuser_token_headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{settings.API_V1_STR}/admin/app/effects/{other['id']}/variants/{other_variant['id']}",
            headers=superuser_token_headers,
        ).status_code
        == 404
    )

    archived_category = client.delete(
        f"{settings.API_V1_STR}/admin/app/effect-categories/{category['id']}",
        headers=superuser_token_headers,
    )
    assert archived_category.status_code == 200
    assert archived_category.json()["message"] == "Draft category deleted"

    archive_slug = f"archive-{uuid.uuid4().hex[:8]}"
    archive_category = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(archive_slug),
    ).json()
    archive_effect = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": archive_category["id"]},
        headers=superuser_token_headers,
    ).json()["data"][0]
    client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{archive_effect['id']}/variants",
        headers=superuser_token_headers,
        json=_variant_payload(),
    )
    client.post(
        f"{settings.API_V1_STR}/admin/app/effects/{archive_effect['id']}/publish",
        headers=superuser_token_headers,
    )
    archived_category = client.delete(
        f"{settings.API_V1_STR}/admin/app/effect-categories/{archive_category['id']}",
        headers=superuser_token_headers,
    )
    assert archived_category.json()["message"] == "Category archived"


def test_catalogue_media_binding_redirect_and_delete_guards(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    assert (
        client.post(
            f"{settings.API_V1_STR}/admin/app/media-assets",
            headers=superuser_token_headers,
            data={"kind": "audio"},
            files={"file": ("audio.mp3", b"audio", "audio/mpeg")},
        ).status_code
        == 422
    )
    poster = client.post(
        f"{settings.API_V1_STR}/admin/app/media-assets",
        headers=superuser_token_headers,
        data={"kind": "poster"},
        files={"file": ("poster.png", b"\x89PNG\r\n\x1a\nposter", "image/png")},
    ).json()
    preview = client.post(
        f"{settings.API_V1_STR}/admin/app/media-assets",
        headers=superuser_token_headers,
        data={"kind": "preview_video"},
        files={
            "file": (
                "preview.mp4",
                b"\x00\x00\x00\x18ftypmp42video",
                "video/mp4",
            )
        },
    ).json()
    media = client.get(
        f"{settings.API_V1_STR}/app/media-assets/{poster['id']}",
        follow_redirects=False,
    )
    assert media.status_code == 307
    assert media.headers["location"].startswith("/uploads/catalog/poster/")
    assert (
        client.get(
            f"{settings.API_V1_STR}/app/media-assets/{uuid.uuid4()}",
            follow_redirects=False,
        ).status_code
        == 404
    )

    slug = f"media-{uuid.uuid4().hex[:8]}"
    category = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(slug),
    ).json()
    effect = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category["id"]},
        headers=superuser_token_headers,
    ).json()["data"][0]
    bound = client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=superuser_token_headers,
        json={
            **_effect_payload(category["id"], effect["slug"]),
            "poster_asset_id": poster["id"],
            "preview_asset_id": preview["id"],
        },
    )
    assert bound.status_code == 200
    assert (
        client.delete(
            f"{settings.API_V1_STR}/admin/app/media-assets/{poster['id']}",
            headers=superuser_token_headers,
        ).status_code
        == 409
    )
    client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}",
        headers=superuser_token_headers,
        json=_effect_payload(category["id"], effect["slug"]),
    )
    assert (
        client.delete(
            f"{settings.API_V1_STR}/admin/app/media-assets/{poster['id']}",
            headers=superuser_token_headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{settings.API_V1_STR}/admin/app/media-assets/{poster['id']}",
            headers=superuser_token_headers,
        ).status_code
        == 404
    )
    deleted_record = db.get(AppManagedMediaAsset, uuid.UUID(poster["id"]))
    assert deleted_record is not None
    assert deleted_record.status == "deleted"


def test_public_effect_detail_filters_and_recommendation_order(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
) -> None:
    slug = f"public-{uuid.uuid4().hex[:8]}"
    category = client.post(
        f"{settings.API_V1_STR}/admin/app/effect-categories",
        headers=superuser_token_headers,
        json=_category_payload(slug),
    ).json()
    effects = client.get(
        f"{settings.API_V1_STR}/admin/app/effects",
        params={"category_id": category["id"]},
        headers=superuser_token_headers,
    ).json()["data"]
    for effect in effects[:2]:
        assert (
            client.post(
                f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/variants",
                headers=superuser_token_headers,
                json=_variant_payload(),
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"{settings.API_V1_STR}/admin/app/effects/{effect['id']}/publish",
                headers=superuser_token_headers,
            ).status_code
            == 200
        )
    updated = client.put(
        f"{settings.API_V1_STR}/admin/app/effects/{effects[0]['id']}",
        headers=superuser_token_headers,
        json=_effect_payload(
            category["id"],
            effects[0]["slug"],
            recommendation_ids=[effects[1]["id"]],
        ),
    )
    assert updated.status_code == 200
    inactive_asset = AppManagedMediaAsset(
        kind="poster",
        object_key=f"catalog/poster/{uuid.uuid4()}.png",
        content_type="image/png",
        size_bytes=10,
        checksum_sha256="0" * 64,
        status="deleted",
    )
    db.add(inactive_asset)
    db.commit()
    first_record = db.get(AppEffect, uuid.UUID(effects[0]["id"]))
    assert first_record is not None
    first_record.poster_asset_id = inactive_asset.id
    db.add(first_record)
    db.commit()
    detail = client.get(f"{settings.API_V1_STR}/app/effects/{effects[0]['slug']}")
    assert detail.status_code == 200
    assert detail.json()["poster_url"] is None
    assert detail.json()["recommendations"] == [effects[1]["slug"]]
    assert "prompt" not in json.dumps(detail.json())

    category_record = db.get(AppEffectCategory, uuid.UUID(category["id"]))
    assert category_record is not None
    category_record.tones_json = "invalid"
    db.add(category_record)
    db.commit()
    catalog = client.get(f"{settings.API_V1_STR}/app/effect-catalog").json()
    public_category = next(
        item for item in catalog["categories"] if item["id"] == category["id"]
    )
    assert public_category["tones"] == ["#476b70", "#18262c", "#98d9de"]

    second_record = db.get(AppEffect, uuid.UUID(effects[1]["id"]))
    assert second_record is not None
    second_record.is_enabled = False
    db.add(second_record)
    db.commit()
    filtered_detail = client.get(
        f"{settings.API_V1_STR}/app/effects/{effects[0]['slug']}"
    )
    assert filtered_detail.json()["recommendations"] == []
    assert (
        client.get(
            f"{settings.API_V1_STR}/app/effects/{effects[1]['slug']}"
        ).status_code
        == 404
    )

    category_record.is_enabled = False
    db.add(category_record)
    db.commit()
    assert (
        client.get(
            f"{settings.API_V1_STR}/app/effects/{effects[0]['slug']}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{settings.API_V1_STR}/app/effects/not-present-{uuid.uuid4()}"
        ).status_code
        == 404
    )


def test_coin_adjustment_rejects_zero_and_unknown_user(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    base = {
        "app_user_id": str(uuid.uuid4()),
        "reason": "Coverage validation",
        "idempotency_key": f"coverage-{uuid.uuid4()}",
    }
    zero = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=superuser_token_headers,
        json={**base, "delta": 0},
    )
    assert zero.status_code == 422
    missing = client.post(
        f"{settings.API_V1_STR}/admin/app/coin-adjustments",
        headers=superuser_token_headers,
        json={**base, "delta": 10},
    )
    assert missing.status_code == 404
