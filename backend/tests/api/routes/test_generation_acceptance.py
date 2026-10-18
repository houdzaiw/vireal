"""Disposable DB, fake Clerk/provider, no live payment or generation."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import HttpUrl, ValidationError
from sqlmodel import delete, select

from app.api.routes import app_video_tasks
from app.core.config import settings
from app.models import (
    AppCoinLedger,
    AppEffect,
    AppEffectCategory,
    AppEffectVariant,
    AppUpload,
    AppUser,
    AppUserIdentity,
    AppUserSession,
    AppVideoTask,
    AppVideoTaskWebhookEvent,
)
from app.services import generation_acceptance as access
from app.services.coin_wallet import (
    adjust_coin_balance,
    get_coin_balance,
    refund_video_task,
)
from app.services.storage import LocalImageStorage
from tests.api.routes.test_app_video_tasks import PNG_BYTES, FakeProvider
from tests.api.routes.test_internal_acceptance import internal  # noqa: F401
from tests.api.routes.test_payment_only_acceptance import no_real_http  # noqa: F401
from tests.api.routes.test_paypal_commerce import signed_headers
from tests.core.test_config_v12 import _settings

AUTH = "/api/v1/app/auth/session"
CONFIG = "/api/v1/app/paypal/config"
UPLOAD = "/api/v1/app/uploads/images"
TASKS = "/api/v1/app/video-tasks"


def proof(path, method="POST", country="CN", *, key=None):
    return {
        "Authorization": "Bearer isolated-clerk-token",
        **signed_headers(path, method, country),
        **({"Idempotency-Key": key} if key else {}),
    }


@pytest.fixture
def acceptance(db, internal, monkeypatch):  # noqa: F811
    clerk, _headers, user_id = internal
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.commit()
    clerk.profile = replace(
        clerk.profile, primary_email=access.GENERATION_ACCEPTANCE_EMAIL
    )
    identity = db.exec(
        select(AppUserIdentity).where(AppUserIdentity.app_user_id == user_id)
    ).one()
    identity.primary_email = clerk.profile.primary_email
    db.add(identity)
    db.commit()
    for name, value in {
        "APP_INTERNAL_ACCEPTANCE_ENABLED": False,
        "APP_GENERATION_ACCEPTANCE_ENABLED": True,
        "APP_GENERATION_ACCEPTANCE_SUBJECT": clerk.claims.subject,
        "APP_GENERATION_ACCEPTANCE_USER_ID": user_id,
        "APP_GENERATION_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC) + timedelta(hours=1),
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
        "APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": False,
        "APP_PAYMENT_ONLY_REPLACEMENT_ENABLED": False,
        "APP_CONTROLLED_CN_ACCOUNT_SETUP_ENABLED": False,
        "APP_LIVE_ACCEPTANCE_SUBJECTS": [],
        "REPLICATE_ENABLED": True,
        "REPLICATE_WEBHOOK_URL": HttpUrl(
            "https://api.example.test/api/v1/webhooks/replicate"
        ),
        "REPLICATE_WEBHOOK_SIGNING_SECRET": "whsec_aXNvbGF0ZWQ=",
        "REPLICATE_POC_MAX_SUBMISSIONS": 2,
        "APP_EFFECT_MAX_DURATION_SECONDS": 10,
        "APP_USER_DAILY_REAL_SUBMISSIONS": 5,
        "APP_USER_MAX_CONCURRENT_VIDEO_TASKS": 1,
        "APP_GLOBAL_DAILY_REAL_SUBMISSIONS": 30,
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(access, "get_clerk_auth_service", lambda: clerk)
    provider = FakeProvider()
    monkeypatch.setattr(app_video_tasks, "get_replicate_video_client", lambda: provider)
    # The tests own this exact catalogue row and restore a preexisting one.
    old = db.exec(select(AppEffect).where(AppEffect.slug == "dance-1")).first()
    old_slug = old.slug if old else None
    if old:
        old.slug = f"isolated-backup-{uuid.uuid4().hex}"
        db.add(old)
        db.commit()
    category = AppEffectCategory(
        slug=f"acceptance-{uuid.uuid4().hex}",
        name_zh="测试",
        name_en="TEST",
        tones_json="[]",
    )
    db.add(category)
    db.flush()
    effect = AppEffect(
        category_id=category.id,
        slug="dance-1",
        title_zh="测试舞蹈",
        title_en="TEST DANCE",
        publish_status="published",
        input_image_count=1,
    )
    db.add(effect)
    db.flush()
    variant = AppEffectVariant(
        effect_id=effect.id,
        duration_seconds=5,
        coin_cost=28,
        model=access.GENERATION_ACCEPTANCE_MODEL,
        model_type="reference-to-video",
        prompt="Isolated safe dance test",
        prompt_version="v1",
    )
    db.add(variant)
    adjust_coin_balance(
        session=db,
        app_user_id=user_id,
        delta=100,
        entry_type="admin_adjustment",
        idempotency_key=str(uuid.uuid4()),
        reason="isolated fixture only",
    )
    db.commit()
    yield clerk, user_id, effect.id, variant.id, provider
    db.rollback()
    db.execute(delete(AppVideoTaskWebhookEvent))
    db.execute(delete(AppVideoTask))
    db.delete(effect)
    db.delete(category)
    db.commit()
    if old:
        old.slug = old_slug
        db.add(old)
        db.commit()


def upload(client, *, headers=None):
    return client.post(
        UPLOAD,
        headers=headers or proof(UPLOAD),
        files={"file": ("qa.png", PNG_BYTES, "image/png")},
    )


def task_body(client, acceptance):
    uploaded = upload(client)
    assert uploaded.status_code == 200, uploaded.text
    return {
        "effect_id": str(acceptance[2]),
        "variant_id": str(acceptance[3]),
        "upload_ids": [uploaded.json()["id"]],
    }


def submit(client, body, key=None):
    return client.post(
        TASKS, headers=proof(TASKS, key=key or str(uuid.uuid4())), json=body
    )


def balance(db, user_id):
    db.expire_all()
    return get_coin_balance(session=db, app_user_id=user_id)


def test_private_config_login_and_no_payment_or_signup(client, db, acceptance):
    clerk, user_id, *_ = acceptance
    public = client.get(CONFIG, headers=signed_headers(CONFIG, "GET", "CN"))
    assert public.status_code == 200 and public.headers["cache-control"] == "no-store"
    assert public.json()["generation_acceptance_sign_in_enabled"]
    assert not public.json()["generation_acceptance_read_allowed"]
    assert not public.json()["generation_acceptance_allowed"]
    assert (
        clerk.claims.subject not in public.text
        and clerk.profile.primary_email not in public.text
    )
    assert str(user_id) not in public.text
    logged_in = client.post(AUTH, headers=proof(AUTH))
    assert logged_in.status_code == 200 and not logged_in.json()["is_new_user"]
    assert logged_in.json()["generation_acceptance_read_allowed"]
    own = client.get(CONFIG, headers=proof(CONFIG, "GET")).json()
    assert own["generation_acceptance_allowed"]
    assert not own["registration_enabled"] and not own["recharge_enabled"]
    assert not own["controlled_registration_enabled"]
    assert (
        not own["internal_sign_in_enabled"] and not own["payment_only_sign_in_enabled"]
    )
    payment = "/api/v1/app/paypal/orders"
    assert (
        client.post(
            payment,
            headers=proof(payment, key=str(uuid.uuid4())),
            json={"product_id": "coins_100"},
        ).status_code
        == 403
    )
    clerk.claims = replace(clerk.claims, subject=f"user_new_{uuid.uuid4().hex}")
    assert client.post(AUTH, headers=proof(AUTH, country="US")).status_code == 403
    assert not db.exec(
        select(AppUserIdentity).where(AppUserIdentity.subject == clerk.claims.subject)
    ).first()


def test_one_submission_same_key_replay_and_new_key_denial(client, db, acceptance):
    body = task_body(client, acceptance)
    key = str(uuid.uuid4())
    first = submit(client, body, key)
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "pending", first.text
    assert first.json()["coin_cost"] == 28
    assert first.json()["resolution"] == "720p" and first.json()["duration"] == 5
    second = submit(client, body, key)
    assert second.status_code == 202 and second.json()["id"] == first.json()["id"]
    assert submit(client, body).status_code == 409
    assert upload(client).status_code == 409
    assert balance(db, acceptance[1]) == 72
    debits = db.exec(
        select(AppCoinLedger).where(
            AppCoinLedger.app_user_id == acceptance[1],
            AppCoinLedger.entry_type == "generation_debit",
        )
    ).all()
    assert len(debits) == 1 and debits[0].delta == -28
    assert len(acceptance[4].calls) == 1
    assert acceptance[4].calls[0]["model"] == access.GENERATION_ACCEPTANCE_MODEL
    assert acceptance[4].calls[0]["aspect_ratio"] == "9:16"
    config = client.get(CONFIG, headers=proof(CONFIG, "GET")).json()
    assert not config["generation_acceptance_allowed"]
    assert config["generation_acceptance_task_id"] == first.json()["id"]


def test_concurrent_new_keys_reserve_only_one_slot(client, db, acceptance):
    body = task_body(client, acceptance)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _n: submit(client, body), range(2)))
    assert sorted(r.status_code for r in results) == [202, 409]
    assert len(acceptance[4].calls) == 1
    assert balance(db, acceptance[1]) == 72


@pytest.mark.parametrize(
    "terminal", ["submission_unknown", "failed", "canceled", "expired"]
)
def test_no_retry_after_timeout_refund_deletion_or_flag_restart(
    client, db, acceptance, monkeypatch, terminal
):
    body = task_body(client, acceptance)
    acceptance[4].timeout = True
    result = submit(client, body)
    assert result.status_code == 202 and result.json()["status"] == "submission_unknown"
    task = db.get(AppVideoTask, uuid.UUID(result.json()["id"]))
    task.status = terminal
    if terminal != "submission_unknown":
        assert refund_video_task(session=db, task=task)
        assert not refund_video_task(session=db, task=task)
    db.add(task)
    db.commit()
    monkeypatch.setattr(settings, "APP_GENERATION_ACCEPTANCE_ENABLED", False)
    monkeypatch.setattr(settings, "APP_GENERATION_ACCEPTANCE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "APP_GENERATION_ACCEPTANCE_EXPIRES_AT",
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert submit(client, body).status_code == 409
    assert upload(client).status_code == 409
    assert len(acceptance[4].calls) == 1
    assert (
        client.get(
            f"{TASKS}/{task.id}", headers=proof(f"{TASKS}/{task.id}", "GET")
        ).status_code
        == 200
    )


@pytest.mark.parametrize("country", ["US", "HK", "XX", "T1"])
def test_no_country_bypass_even_for_selected_user(client, acceptance, country):
    assert acceptance[1]
    assert upload(client, headers=proof(UPLOAD, country=country)).status_code == 403
    config = client.get(CONFIG, headers=proof(CONFIG, "GET", country)).json()
    assert not config["generation_acceptance_allowed"]
    assert not config["generation_acceptance_sign_in_enabled"]


@pytest.mark.parametrize(
    "issue",
    [
        "unsigned",
        "forged",
        "wrong_subject",
        "wrong_user",
        "wrong_issuer",
        "wrong_email",
        "unverified",
        "revoked",
        "disabled",
        "hold",
        "profile_email",
        "profile_unverified",
        "profile_error",
        "token_error",
    ],
)
def test_identity_region_and_profile_fail_closed(
    client, db, acceptance, monkeypatch, issue
):
    clerk, user_id, *_ = acceptance
    headers = proof(UPLOAD)
    if issue == "unsigned":
        headers = {"Authorization": "Bearer isolated-clerk-token", "CF-IPCountry": "CN"}
    elif issue == "forged":
        headers["x-vireal-edge-signature"] = "0" * 64
    elif issue in {"wrong_subject", "wrong_user", "wrong_issuer"}:
        name, value = {
            "wrong_subject": ("APP_GENERATION_ACCEPTANCE_SUBJECT", "user_other"),
            "wrong_user": ("APP_GENERATION_ACCEPTANCE_USER_ID", uuid.uuid4()),
            "wrong_issuer": ("CLERK_ISSUER_URL", HttpUrl("https://other.example.test")),
        }[issue]
        monkeypatch.setattr(settings, name, value)
    elif issue in {"wrong_email", "unverified"}:
        identity = db.exec(
            select(AppUserIdentity).where(AppUserIdentity.app_user_id == user_id)
        ).one()
        if issue == "wrong_email":
            identity.primary_email = "another@example.com"
        else:
            identity.email_verified = False
        db.add(identity)
        db.commit()
    elif issue == "revoked":
        local = db.exec(
            select(AppUserSession).where(AppUserSession.app_user_id == user_id)
        ).one()
        local.revoked_at = datetime.now(UTC)
        db.add(local)
        db.commit()
    elif issue in {"disabled", "hold"}:
        user = db.get(AppUser, user_id)
        if issue == "disabled":
            user.status = "disabled"
        else:
            user.payment_hold = True
        db.add(user)
        db.commit()
    elif issue == "profile_email":
        clerk.profile = replace(clerk.profile, primary_email="other@example.com")
    elif issue == "profile_unverified":
        clerk.profile = replace(clerk.profile, email_verified=False)
    elif issue == "profile_error":
        from app.services.clerk_auth import ClerkAPIError

        def broken(_subject):
            raise ClerkAPIError("isolated API failure")

        monkeypatch.setattr(clerk, "get_user_profile", broken)
    else:
        from app.services.clerk_auth import ClerkAuthenticationError

        def invalid(_token):
            raise ClerkAuthenticationError("isolated invalid token")

        monkeypatch.setattr(clerk, "verify_session_token", invalid)
    assert upload(client, headers=headers).status_code in {403, 409}
    assert not acceptance[4].calls


def test_another_existing_overseas_user_cannot_generate(client, db, acceptance):
    # Same Clerk service, but a distinct existing verified business identity.
    clerk, _user_id, *_ = acceptance
    user = AppUser(account_type="clerk")
    db.add(user)
    db.flush()
    claims = replace(
        clerk.claims,
        subject=f"user_other_{uuid.uuid4().hex}",
        session_id=f"session_other_{uuid.uuid4().hex}",
    )
    from app.services.app_identity import hash_clerk_session_id

    db.add(
        AppUserIdentity(
            app_user_id=user.id,
            subject=claims.subject,
            issuer=claims.issuer,
            primary_email="other@example.com",
            email_verified=True,
        )
    )
    db.add(
        AppUserSession(
            app_user_id=user.id,
            session_id_hash=hash_clerk_session_id(claims.session_id),
        )
    )
    db.commit()
    clerk.claims = claims
    assert upload(client, headers=proof(UPLOAD, country="US")).status_code == 403
    result = client.post(
        TASKS,
        headers=proof(TASKS, country="US", key=str(uuid.uuid4())),
        json={
            "effect_id": str(acceptance[2]),
            "variant_id": str(acceptance[3]),
            "upload_ids": [str(uuid.uuid4())],
        },
    )
    assert result.status_code == 403 and not acceptance[4].calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration_seconds", 10),
        ("coin_cost", 29),
        ("model", "minimax/video-01"),
        ("prompt_version", "v2"),
        ("is_enabled", False),
    ],
)
def test_variant_cannot_change_duration_price_or_model(
    client, db, acceptance, field, value
):
    body = task_body(client, acceptance)
    variant = db.get(AppEffectVariant, acceptance[3])
    setattr(variant, field, value)
    db.add(variant)
    db.commit()
    assert submit(client, body).status_code in {403, 409}
    assert not acceptance[4].calls
    assert balance(db, acceptance[1]) == 100


def test_cross_owner_and_legacy_requests_do_not_consume_slot(client, db, acceptance):
    body = task_body(client, acceptance)
    uploaded = db.get(AppUpload, uuid.UUID(body["upload_ids"][0]))
    other = AppUser()
    db.add(other)
    db.flush()
    uploaded.app_user_id = other.id
    db.add(uploaded)
    db.commit()
    assert submit(client, body).status_code == 400
    assert (
        submit(
            client,
            {
                "template_id": "dance",
                "mode": "advanced",
                "duration": 5,
                "upload_ids": body["upload_ids"],
            },
        ).status_code
        == 409
    )
    assert not acceptance[4].calls


def test_expiry_rechecked_after_user_lock_and_upload_io(
    client, db, acceptance, monkeypatch
):
    original = LocalImageStorage.store_app_image
    deleted = []

    def slow_storage(self, **kwargs):
        stored = original(self, **kwargs)
        monkeypatch.setattr(
            settings,
            "APP_GENERATION_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        return stored

    monkeypatch.setattr(LocalImageStorage, "store_app_image", slow_storage)
    monkeypatch.setattr(
        LocalImageStorage, "delete_object", lambda _self, key: deleted.append(key)
    )
    assert upload(client).status_code == 403
    assert len(deleted) == 1
    assert not db.exec(
        select(AppUpload).where(AppUpload.app_user_id == acceptance[1])
    ).all()
    monkeypatch.setattr(LocalImageStorage, "store_app_image", original)
    monkeypatch.setattr(
        settings,
        "APP_GENERATION_ACCEPTANCE_EXPIRES_AT",
        datetime.now(UTC) + timedelta(hours=1),
    )
    body = task_body(client, acceptance)
    lock = app_video_tasks.lock_commercial_user

    def slow_lock(session, user):
        locked = lock(session, user)
        monkeypatch.setattr(
            settings,
            "APP_GENERATION_ACCEPTANCE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        return locked

    monkeypatch.setattr(app_video_tasks, "lock_commercial_user", slow_lock)
    assert submit(client, body).status_code == 403
    assert not acceptance[4].calls
    assert balance(db, acceptance[1]) == 100
    assert client.post(AUTH, headers=proof(AUTH)).json()[
        "generation_acceptance_read_allowed"
    ]


def test_global_pause_also_blocks_uploads_without_any_acceptance_mode(
    client, acceptance, monkeypatch
):
    assert acceptance[1]
    monkeypatch.setattr(settings, "APP_GENERATION_ACCEPTANCE_ENABLED", False)
    assert upload(client, headers=proof(UPLOAD, country="US")).status_code == 503
    monkeypatch.setattr(settings, "APP_VIDEO_SUBMISSIONS_ENABLED", True)
    assert upload(client, headers=proof(UPLOAD, country="US")).status_code == 200


def test_expired_window_preserves_read_and_same_key_replay(
    client, db, acceptance, monkeypatch
):
    body = task_body(client, acceptance)
    key = str(uuid.uuid4())
    first = submit(client, body, key)
    assert first.status_code == 202
    monkeypatch.setattr(
        settings,
        "APP_GENERATION_ACCEPTANCE_EXPIRES_AT",
        datetime.now(UTC) - timedelta(seconds=1),
    )
    replay = submit(client, body, key)
    assert replay.status_code == 202 and replay.json()["id"] == first.json()["id"]
    assert submit(client, body).status_code == 403
    assert upload(client).status_code == 403
    assert (
        client.get(
            f"{TASKS}/{first.json()['id']}", headers=proof(TASKS, "GET")
        ).status_code
        == 200
    )
    assert len(acceptance[4].calls) == 1 and balance(db, acceptance[1]) == 72


def test_global_provider_cap_is_not_bypassed(client, db, acceptance):
    body = task_body(client, acceptance)
    other = AppUser()
    db.add(other)
    db.flush()
    for _ in range(2):
        db.add(
            AppVideoTask(
                app_user_id=other.id,
                idempotency_key=str(uuid.uuid4()),
                template_id="dance",
                mode="advanced",
                upload_ids_json="[]",
                model="wan-video/wan-2.7-r2v",
                execution_type="wan",
                status="submission_unknown",
                duration=5,
                seed=1,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
    db.commit()
    assert submit(client, body).status_code == 409
    assert not acceptance[4].calls and balance(db, acceptance[1]) == 100
    assert not db.exec(
        select(AppVideoTask).where(AppVideoTask.app_user_id == acceptance[1])
    ).all()


def generation_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "APP_AUTH_MODE": "clerk",
        "CLERK_ISSUER_URL": "https://clerk.example.test",
        "CLERK_JWKS_URL": "https://clerk.example.test/jwks",
        "CLERK_AUDIENCE": "vireal",
        "CLERK_SECRET_KEY": "isolated-clerk-key",
        "CLERK_AUTHORIZED_PARTIES": ["https://app.example.test"],
        "APP_GENERATION_ACCEPTANCE_ENABLED": True,
        "APP_GENERATION_ACCEPTANCE_SUBJECT": "user_isolated",
        "APP_GENERATION_ACCEPTANCE_USER_ID": uuid.uuid4(),
        "APP_GENERATION_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC) + timedelta(hours=1),
        "APP_REGION_ENFORCEMENT_ENABLED": True,
        "APP_EDGE_SIGNING_SECRET": "isolated-generation-signing-key-32-characters",
        "REPLICATE_ENABLED": True,
        "REPLICATE_API_TOKEN": "isolated-provider-token",
        "REPLICATE_WEBHOOK_URL": "https://api.example.test/api/v1/webhooks/replicate",
        "REPLICATE_WEBHOOK_SIGNING_SECRET": "whsec_aXNvbGF0ZWQ=",
        "REPLICATE_POC_MAX_SUBMISSIONS": 2,
        "APP_IMAGE_STORAGE_BACKEND": "r2",
        "R2_ENDPOINT_URL": "https://isolated.r2.cloudflarestorage.com",
        "R2_ACCESS_KEY_ID": "isolated-key",
        "R2_SECRET_ACCESS_KEY": "isolated-secret",
        "R2_BUCKET_NAME": "isolated-bucket",
        "APP_VIDEO_SUBMISSIONS_ENABLED": False,
        "ADMIN_PUBLIC_SIGNUP_ENABLED": False,
        "LOCAL_DEMO_ENABLED": False,
        "APP_LEGACY_VIDEO_TASKS_ENABLED": False,
    }
    values.update(overrides)
    return _settings(**values)


def test_default_off_and_expired_startup_does_not_break_settlement():
    assert not _settings().APP_GENERATION_ACCEPTANCE_ENABLED
    assert generation_settings().generation_acceptance_configuration_safe()
    assert generation_settings(
        APP_GENERATION_ACCEPTANCE_EXPIRES_AT=datetime.now(UTC) - timedelta(hours=1)
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"APP_GENERATION_ACCEPTANCE_USER_ID": None},
        {"APP_GENERATION_ACCEPTANCE_SUBJECT": "user_a,user_b"},
        {"APP_GENERATION_ACCEPTANCE_EXPIRES_AT": None},
        {
            "APP_GENERATION_ACCEPTANCE_EXPIRES_AT": datetime.now(UTC)
            + timedelta(hours=3)
        },
        {"APP_GENERATION_ACCEPTANCE_EXPIRES_AT": datetime.now()},
        {"ENVIRONMENT": "staging"},
        {"APP_VIDEO_SUBMISSIONS_ENABLED": True},
        {"REPLICATE_ENABLED": False},
        {"REPLICATE_POC_MAX_SUBMISSIONS": 0},
        {"REPLICATE_POC_MAX_SUBMISSIONS": 3},
        {"APP_PUBLIC_REGISTRATION_ENABLED": True},
        {"APP_CONTROLLED_REGISTRATION_ENABLED": True},
        {"APP_INTERNAL_ACCEPTANCE_ENABLED": True},
        {"APP_LIVE_ACCEPTANCE_ENABLED": True},
        {"APP_PAYMENT_ONLY_ACCEPTANCE_ENABLED": True},
        {"APP_PAYMENT_ONLY_REPLACEMENT_ENABLED": True},
        {"PAYPAL_ENABLED": True},
        {"APP_COMMERCE_TERMS_APPROVED": True},
        {"ADMIN_PUBLIC_SIGNUP_ENABLED": True},
        {"LOCAL_DEMO_ENABLED": True},
        {"APP_LEGACY_VIDEO_TASKS_ENABLED": True},
        {"APP_REGION_ENFORCEMENT_ENABLED": False},
        {"APP_EDGE_SIGNING_SECRET": "short"},
        {"APP_USER_DAILY_REAL_SUBMISSIONS": 6},
        {"APP_USER_MAX_CONCURRENT_VIDEO_TASKS": 2},
        {"APP_GLOBAL_DAILY_REAL_SUBMISSIONS": 31},
        {"APP_EFFECT_MAX_DURATION_SECONDS": 15},
    ],
)
def test_unsafe_configuration_rejected(overrides):
    with pytest.raises(ValidationError):
        generation_settings(**overrides)


@pytest.mark.parametrize(
    "name,value",
    [
        ("APP_VIDEO_SUBMISSIONS_ENABLED", True),
        ("PAYPAL_ENABLED", True),
        ("APP_PUBLIC_REGISTRATION_ENABLED", True),
        ("APP_INTERNAL_ACCEPTANCE_ENABLED", True),
        ("APP_GENERATION_ACCEPTANCE_EXPIRES_AT", None),
        ("REPLICATE_POC_MAX_SUBMISSIONS", 0),
    ],
)
def test_runtime_unsafe_settings_are_not_an_escape_hatch(
    client, acceptance, monkeypatch, name, value
):
    assert acceptance[1]
    monkeypatch.setattr(settings, name, value)
    assert upload(client).status_code == 403
    config = client.get(CONFIG, headers=proof(CONFIG, "GET")).json()
    assert not config["registration_enabled"] and not config["recharge_enabled"]
    assert not config["generation_acceptance_allowed"]
