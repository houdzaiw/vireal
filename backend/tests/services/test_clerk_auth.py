from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import (
    STAGING_LOGIN_ACCEPTANCE_ISSUER,
    STAGING_LOGIN_ACCEPTANCE_ORIGIN,
    settings,
)
from app.services.clerk_auth import (
    ClerkAuthenticationError,
    ClerkAuthService,
    get_clerk_auth_service,
)


class StaticSigningKey:
    def __init__(self, key: object) -> None:
        self.key = key


def build_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_missing_authorized_party: bool = False,
) -> tuple[ClerkAuthService, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    service = ClerkAuthService(
        issuer_url="https://clerk.example.test",
        jwks_url="https://clerk.example.test/.well-known/jwks.json",
        secret_key="sk_test_example",
        authorized_parties=("https://app.example.test",),
        audience="vireal-api",
        allow_missing_authorized_party=allow_missing_authorized_party,
    )
    monkeypatch.setattr(
        service.jwks_client,
        "get_signing_key_from_jwt",
        lambda _token: StaticSigningKey(private_key.public_key()),
    )
    return service, private_key


def encode_token(
    private_key: object,
    *,
    kid: str = "key-one",
    omit_authorized_party: bool = False,
    **overrides: object,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "iss": "https://clerk.example.test",
        "sub": "user_test",
        "sid": "sess_test",
        "azp": "https://app.example.test",
        "aud": "vireal-api",
        "iat": now,
        "nbf": now - timedelta(seconds=1),
        "exp": now + timedelta(minutes=1),
    }
    payload.update(overrides)
    if omit_authorized_party:
        del payload["azp"]
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def test_verify_clerk_session_token(monkeypatch: pytest.MonkeyPatch) -> None:
    service, private_key = build_service(monkeypatch)
    claims = service.verify_session_token(encode_token(private_key))

    assert claims.subject == "user_test"
    assert claims.session_id == "sess_test"
    assert claims.authorized_party == "https://app.example.test"


def test_verify_clerk_session_token_after_jwks_key_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, first_private_key = build_service(monkeypatch)
    second_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_keys = {
        "key-one": first_private_key.public_key(),
        "key-two": second_private_key.public_key(),
    }

    def signing_key(token: str) -> StaticSigningKey:
        kid = jwt.get_unverified_header(token)["kid"]
        return StaticSigningKey(public_keys[kid])

    monkeypatch.setattr(service.jwks_client, "get_signing_key_from_jwt", signing_key)

    first = service.verify_session_token(
        encode_token(first_private_key, kid="key-one", sub="user_before_rotation")
    )
    second = service.verify_session_token(
        encode_token(second_private_key, kid="key-two", sub="user_after_rotation")
    )

    assert first.subject == "user_before_rotation"
    assert second.subject == "user_after_rotation"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"iss": "https://wrong.example.test"}, "Invalid or expired"),
        ({"aud": "wrong-audience"}, "Invalid or expired"),
        ({"azp": "https://evil.example.test"}, "unauthorized party"),
        ({"azp": None}, "Invalid or expired"),
        ({"nbf": None}, "Invalid or expired"),
        ({"exp": None}, "Invalid or expired"),
        (
            {"exp": datetime.now(UTC) - timedelta(minutes=1)},
            "Invalid or expired",
        ),
    ],
)
def test_rejects_invalid_clerk_token(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    message: str,
) -> None:
    service, private_key = build_service(monkeypatch)
    with pytest.raises(ClerkAuthenticationError, match=message):
        service.verify_session_token(encode_token(private_key, **overrides))


@pytest.mark.parametrize(
    ("config_overrides", "allowed"),
    [
        pytest.param({}, True, id="staging"),
        pytest.param({"environment": "production"}, False, id="production"),
        pytest.param({"environment": "local"}, False, id="local"),
        pytest.param(
            {"issuer": "https://another-clerk.example.test"},
            False,
            id="different-issuer",
        ),
        pytest.param(
            {"jwks_path": "/unexpected-jwks.json"}, False, id="different-jwks"
        ),
        pytest.param(
            {"party": "https://app.example.test"}, False, id="different-origin"
        ),
    ],
)
def test_missing_authorized_party_is_limited_to_staging_clerk(
    monkeypatch: pytest.MonkeyPatch,
    config_overrides: dict[str, str],
    allowed: bool,
) -> None:
    issuer = config_overrides.get("issuer", STAGING_LOGIN_ACCEPTANCE_ISSUER)
    jwks_path = config_overrides.get("jwks_path", "/.well-known/jwks.json")
    party = config_overrides.get("party", STAGING_LOGIN_ACCEPTANCE_ORIGIN)
    monkeypatch.setattr(
        settings, "ENVIRONMENT", config_overrides.get("environment", "staging")
    )
    monkeypatch.setattr(settings, "CLERK_ISSUER_URL", issuer)
    monkeypatch.setattr(settings, "CLERK_JWKS_URL", issuer + jwks_path)
    monkeypatch.setattr(settings, "CLERK_AUDIENCE", "vireal-api")
    monkeypatch.setattr(settings, "CLERK_SECRET_KEY", "synthetic-test-secret")
    monkeypatch.setattr(settings, "CLERK_AUTHORIZED_PARTIES", [party])
    get_clerk_auth_service.cache_clear()
    try:
        service = get_clerk_auth_service()
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        monkeypatch.setattr(
            service.jwks_client,
            "get_signing_key_from_jwt",
            lambda _token: StaticSigningKey(private_key.public_key()),
        )
        web_token = encode_token(private_key, iss=issuer, azp=party)
        assert service.verify_session_token(web_token).authorized_party == party

        native_token = encode_token(private_key, iss=issuer, omit_authorized_party=True)
        if allowed:
            assert service.verify_session_token(native_token).authorized_party is None
        else:
            with pytest.raises(ClerkAuthenticationError, match="Invalid or expired"):
                service.verify_session_token(native_token)
    finally:
        get_clerk_auth_service.cache_clear()


@pytest.mark.parametrize(
    ("omit_authorized_party", "overrides"),
    [
        (False, {"azp": None}),
        (False, {"azp": ""}),
        (False, {"azp": ["https://app.example.test"]}),
        (False, {"azp": "https://different.example.test"}),
        (True, {"aud": "other-api"}),
        (True, {"iss": "https://different.example.test"}),
        (True, {"sts": "pending"}),
        (True, {"exp": datetime.now(UTC) - timedelta(minutes=1)}),
    ],
)
def test_staging_still_rejects_invalid_session_claims(
    monkeypatch: pytest.MonkeyPatch,
    omit_authorized_party: bool,
    overrides: dict[str, object],
) -> None:
    service, private_key = build_service(
        monkeypatch, allow_missing_authorized_party=True
    )
    token = encode_token(
        private_key, omit_authorized_party=omit_authorized_party, **overrides
    )
    with pytest.raises(ClerkAuthenticationError):
        service.verify_session_token(token)


@pytest.mark.parametrize(
    ("verification_strategy", "external_provider", "expected"),
    [
        ("email_code", None, ("email",)),
        ("from_oauth_google", "oauth_google", ("google",)),
        ("from_oauth_apple", "oauth_apple", ("apple",)),
        ("email_code", "oauth_google", ("email", "google")),
    ],
)
def test_clerk_profile_reports_actual_login_methods(
    monkeypatch: pytest.MonkeyPatch,
    verification_strategy: str,
    external_provider: str | None,
    expected: tuple[str, ...],
) -> None:
    service, _private_key = build_service(monkeypatch)
    external_accounts = [{"provider": external_provider}] if external_provider else []
    monkeypatch.setattr(
        service,
        "_request",
        lambda *_args, **_kwargs: {
            "primary_email_address_id": "email_primary",
            "email_addresses": [
                {
                    "id": "email_primary",
                    "email_address": "User@Example.com",
                    "verification": {
                        "status": "verified",
                        "strategy": verification_strategy,
                    },
                }
            ],
            "external_accounts": external_accounts,
        },
    )

    profile = service.get_user_profile("user_test")

    assert profile.primary_email == "user@example.com"
    assert profile.providers == expected
