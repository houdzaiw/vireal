# ruff: noqa: ARG001
import io
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlmodel import Session, delete, select

from app.api.routes import app_media
from app.core.config import settings
from app.core.db import engine
from app.models import AppManagedMediaAsset
from app.models_resources import (
    AppMediaReadGrant,
    AppResourceAttempt,
    AppResourcePolicy,
)
from app.services import resource_limits as limits
from app.services.media_grants import issue_read_url
from app.services.storage import ImageStorageError, R2ImageStorage

SCOPE = "synthetic-resource-allocation"
PNG = b"\x89PNG\r\n\x1a\nexample"


@pytest.fixture
def policy(db, monkeypatch):
    monkeypatch.setattr(settings, "APP_RESOURCE_GUARD_ENABLED", True)
    monkeypatch.setattr(settings, "APP_RESOURCE_SCOPE", SCOPE)
    monkeypatch.setattr(settings, "APP_MEDIA_READ_BASE_URL", "https://api.example.com")
    monkeypatch.setattr(settings, "APP_IMAGE_STORAGE_BACKEND", "r2")
    now = datetime.now(UTC)
    caps = dict.fromkeys(limits.METRICS, 100)
    caps.update(
        generations=2,
        uploads=2,
        upload_bytes=10_000_000,
        delivery_bytes=10 * settings.MAX_GENERATED_VIDEO_BYTES,
        storage_bytes=10 * settings.MAX_GENERATED_VIDEO_BYTES + 10_000_000,
        read_bytes=100 * settings.MAX_GENERATED_VIDEO_BYTES,
        read_bytes_delivery=100 * settings.MAX_GENERATED_VIDEO_BYTES,
    )
    row = AppResourcePolicy(
        scope=SCOPE,
        enabled=True,
        starts_at=now - timedelta(minutes=1),
        admission_until=now + timedelta(hours=1),
        delivery_until=now + timedelta(hours=2),
        direct_urls_expired_at=now - timedelta(seconds=1),
        evidence="synthetic allowance",
        account_evidence="synthetic all-consumer allocation",
        initial_storage_bytes=0,
        pending_tasks_at_start=0,
        model="wan-video/wan-2.7-r2v",
        duration=5,
        caps=caps,
        used={},
    )
    db.add(row)
    db.commit()
    yield row
    db.rollback()
    for model in [AppMediaReadGrant, AppResourceAttempt, AppResourcePolicy]:
        db.exec(delete(model).where(model.scope == SCOPE))
    db.exec(
        delete(AppManagedMediaAsset).where(
            AppManagedMediaAsset.object_key == "vireal/catalog/video/synthetic.mp4"
        )
    )
    db.commit()


def used():
    with Session(engine) as s:
        return dict(s.get(AppResourcePolicy, SCOPE).used)


def change(**kwargs):
    with Session(engine) as s:
        row = s.get(AppResourcePolicy, SCOPE)
        for k, v in kwargs.items():
            setattr(row, k, v)
        s.add(row)
        s.commit()


def test_unknown_outcome_and_caller_rollback_hold_allocation(policy, db):
    limits.consume(
        "put",
        {"uploads": 1, "upload_bytes": 10, "storage_bytes": 10, "class_a_upload": 1},
        admission=True,
    )
    db.rollback()
    assert used()["uploads"] == 1
    assert used()["storage_bytes"] == 10
    with Session(engine) as fresh:
        assert (
            len(
                fresh.exec(
                    select(AppResourceAttempt).where(AppResourceAttempt.scope == SCOPE)
                ).all()
            )
            == 1
        )


def test_concurrent_sessions_cannot_oversubscribe(policy):
    def attempt(_):
        try:
            limits.consume("upload", {"uploads": 1}, admission=True)
            return True
        except HTTPException as e:
            assert e.status_code == 429
            return False

    with ThreadPoolExecutor(max_workers=6) as p:
        result = list(p.map(attempt, range(10)))
    assert sum(result) == 2
    assert used()["uploads"] == 2


def test_counters_survive_new_process(policy):
    limits.consume("one", {"uploads": 1})
    env = dict(os.environ, APP_RESOURCE_SCOPE=SCOPE, APP_RESOURCE_GUARD_ENABLED="true")
    code = "from app.services.resource_limits import consume; consume('child', {'uploads':1})"
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, timeout=15
    )
    assert result.returncode == 0
    assert used()["uploads"] == 2
    with pytest.raises(HTTPException):
        limits.consume("again", {"uploads": 1})


@pytest.mark.parametrize(
    "fault",
    [
        "disabled",
        "expired",
        "new-window-ended",
        "missing-evidence",
        "missing-account",
        "old-url",
        "missing-cap",
        "bool-cap",
        "insufficient-delivery",
        "baseline-not-held",
    ],
)
def test_bad_policy_denies_before_operation(policy, fault):
    caps = dict(policy.caps)
    update = {}
    if fault == "disabled":
        update["enabled"] = False
    elif fault == "expired":
        update["delivery_until"] = datetime.now(UTC) - timedelta(seconds=1)
    elif fault == "new-window-ended":
        update["admission_until"] = datetime.now(UTC) - timedelta(seconds=1)
    elif fault == "missing-evidence":
        update["evidence"] = ""
    elif fault == "missing-account":
        update["account_evidence"] = ""
    elif fault == "old-url":
        update["direct_urls_expired_at"] = datetime.now(UTC) + timedelta(minutes=30)
    elif fault == "missing-cap":
        caps.pop("reads")
        update["caps"] = caps
    elif fault == "bool-cap":
        caps["reads"] = True
        update["caps"] = caps
    elif fault == "insufficient-delivery":
        caps["class_a_delivery"] = 1
        update["caps"] = caps
    else:
        update["initial_storage_bytes"] = 1
    change(**update)
    with pytest.raises(HTTPException):
        limits.consume("new", {"uploads": 1}, admission=True)
    assert used().get("uploads", 0) == 0


def test_new_upload_exhaustion_does_not_use_delivery_tranche(policy):
    limits.consume("uploads", {"uploads": 2, "class_a_upload": 2}, admission=True)
    change(admission_until=datetime.now(UTC) - timedelta(seconds=1))
    limits.consume(
        "old-task", {"class_a_delivery": 1, "delivery_bytes": 8, "storage_bytes": 8}
    )
    limits.consume("old-read", {"reads": 1, "read_bytes": 8})
    assert used()["class_a_delivery"] == 1


def test_generation_model_duration_total_are_enforced(policy):
    with pytest.raises(HTTPException):
        limits.reserve_generation("other", 5)
    with pytest.raises(HTTPException):
        limits.reserve_generation(policy.model, 10)
    limits.reserve_generation(policy.model, 5)
    limits.reserve_generation(policy.model, 5)
    with pytest.raises(HTTPException):
        limits.reserve_generation(policy.model, 5)
    assert used()["generations"] == 2


def test_missing_policy_never_silently_disables_guard(policy, monkeypatch):
    monkeypatch.setattr(settings, "APP_RESOURCE_SCOPE", "not-allocated")
    with pytest.raises(HTTPException):
        limits.consume("read", {"reads": 1})


class FakeR2:
    def __init__(self):
        self.puts = 0
        self.gets = 0
        self.fail = False

    def put_object(self, **kwargs):
        self.puts += 1
        if self.fail:
            raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject")

    def upload_fileobj(self, *args, **kwargs):
        raise AssertionError("Multipart must not be used")

    def generate_presigned_url(self, *args, **kwargs):
        raise AssertionError("Direct R2 links must not escape")

    def get_object(self, **kwargs):
        self.gets += 1
        content = b"12345678"
        headers = {}
        if kwargs.get("Range"):
            assert kwargs["Range"] == "bytes=0-2"
            content = content[:3]
            headers["ContentRange"] = "bytes 0-2/8"
        return {
            "Body": io.BytesIO(content),
            "ContentLength": len(content),
            "ContentType": "video/mp4",
            **headers,
        }

    def delete_object(self, **kwargs):
        pass


def storage(client):
    return R2ImageStorage(
        client=client, bucket_name="synthetic", object_prefix="vireal"
    )


def test_write_failure_is_charged_and_no_io_after_exhaustion(policy):
    client = FakeR2()
    client.fail = True
    s = storage(client)
    for _ in range(2):
        with pytest.raises(ImageStorageError):
            s.store_app_image(
                app_user_id=uuid.uuid4(), content=PNG, uploaded_content_type="image/png"
            )
    with pytest.raises(ImageStorageError) as e:
        s.store_app_image(
            app_user_id=uuid.uuid4(), content=PNG, uploaded_content_type="image/png"
        )
    assert e.value.status_code == 429
    assert client.puts == 2
    assert used()["upload_bytes"] == 2 * len(PNG)


def test_generated_video_uses_single_metered_put(policy, tmp_path):
    p = tmp_path / "video.mp4"
    p.write_bytes(b"12345678")
    c = FakeR2()
    s = storage(c)
    for _ in range(2):
        s.store_video_file(
            app_user_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            file_path=p,
            content_type="video/mp4",
        )
    assert c.puts == 2 and used()["class_a_delivery"] == 2
    assert used()["storage_bytes"] == 16


@pytest.fixture
def media(policy, db, monkeypatch):
    asset = AppManagedMediaAsset(
        kind="preview_video",
        object_key="vireal/catalog/video/synthetic.mp4",
        content_type="video/mp4",
        size_bytes=8,
        checksum_sha256="0" * 64,
    )
    db.add(asset)
    db.commit()
    c = FakeR2()
    s = storage(c)
    monkeypatch.setattr(app_media, "get_image_storage", lambda: s)
    url = s.create_object_read_url(asset.object_key, expires_in=60)
    assert url.startswith("https://api.example.com/api/v1/app/media/read?token=")
    return asset, c, "/api/v1/app/media/read?" + urlsplit(url).query


def test_reused_signed_url_each_get_is_metered_and_range_supported(media, client):
    asset, c, url = media
    assert client.get(url).status_code == 200
    response = client.get(url, headers={"Range": "bytes=0-2"})
    assert response.status_code == 206 and response.content == b"123"
    assert response.headers["content-range"] == "bytes 0-2/8"
    assert c.gets == 2 and used()["reads"] == 2
    assert client.head(url).status_code == 405
    assert c.gets == 2


@pytest.mark.parametrize(
    "range_value", ["bytes=0-1,4-5", "bytes=a-b", "bytes=-", "bytes=0-2\r\nX: 1"]
)
def test_invalid_ranges_do_not_hit_r2(media, client, range_value):
    _, c, url = media
    response = client.get(url, headers={"Range": range_value})
    assert response.status_code == 416 and c.gets == 0


def test_tampered_expired_revoked_tokens_do_not_hit_r2(media, client, db):
    asset, c, url = media
    token = parse_qs(urlsplit(url).query)["token"][0]
    assert (
        client.get("/api/v1/app/media/read?token=" + token[:-5] + "abcde").status_code
        == 404
    )
    db.exec(delete(AppMediaReadGrant))
    db.commit()
    assert client.get(url).status_code == 404 and c.gets == 0
    fresh = issue_read_url(asset.object_key, 60)
    asset.status = "deleted"
    db.add(asset)
    db.commit()
    assert (
        client.get("/api/v1/app/media/read?" + urlsplit(fresh).query).status_code == 404
    )
    assert c.gets == 0


def test_read_limit_blocks_before_r2_but_keeps_accounting(media, client, policy):
    _, c, url = media
    caps = dict(policy.caps)
    caps["reads"] = 1
    change(caps=caps)
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 429
    assert c.gets == 1 and used()["reads"] == 1


def test_expired_database_grant_cannot_use_other_valid_token(media, client, db):
    _, c, url = media
    grant = db.exec(select(AppMediaReadGrant)).one()
    grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.add(grant)
    db.commit()
    assert client.get(url).status_code == 404
    assert c.gets == 0


def test_attempt_limit_does_not_reset_on_other_metric(policy):
    caps = dict(policy.caps)
    caps["attempts"] = 1
    change(caps=caps)
    limits.consume("read", {"reads": 1})
    with pytest.raises(HTTPException) as exc:
        limits.consume("grant", {"grants": 1})
    assert exc.value.status_code == 429
    assert used()["attempts"] == 1


def test_dollar_pause_does_not_disable_old_delivery_allocation(policy, db):
    from app.models_operations import AppBudgetWindow

    window = db.exec(select(AppBudgetWindow)).one()
    window.state = "paused"
    db.add(window)
    db.commit()
    limits.consume(
        "pending-video",
        {"class_a_delivery": 1, "delivery_bytes": 8, "storage_bytes": 8},
    )
    assert used()["class_a_delivery"] == 1


def test_user_read_and_grant_exhaustion_cannot_starve_provider(media, client, policy):
    asset, c, url = media
    caps = dict(policy.caps)
    caps["reads"] = 1
    caps["grants"] = 1
    change(caps=caps)
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 429
    with pytest.raises(HTTPException):
        issue_read_url(asset.object_key, 60)
    provider = issue_read_url(asset.object_key, 60, delivery=True)
    provider_path = "/api/v1/app/media/read?" + urlsplit(provider).query
    assert client.get(provider_path).status_code == 200
    assert used()["reads_delivery"] == 1 and used()["grants_delivery"] == 1
    # A caller-supplied query flag cannot elevate an exhausted user grant.
    assert client.get(url + "&delivery=true").status_code == 429
    assert c.gets == 2


def test_guarded_provider_inputs_cannot_escape_with_absolute_r2_url(policy):
    from app.services.storage import create_provider_read_url

    with pytest.raises(ValueError, match="managed metered"):
        create_provider_read_url(
            "https://synthetic.r2.cloudflarestorage.com/object?sig=synthetic"
        )


def test_resource_window_cannot_extend_business_beyond_72_hours(policy):
    change(
        admission_until=datetime.now(UTC) + timedelta(hours=73),
        delivery_until=datetime.now(UTC) + timedelta(hours=74),
    )
    with pytest.raises(HTTPException):
        limits.consume("upload", {"uploads": 1}, admission=True)
    assert used().get("uploads", 0) == 0
