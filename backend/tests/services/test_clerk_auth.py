from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.clerk_auth import ClerkAuthenticationError, ClerkAuthService


class StaticSigningKey:
    def __init__(self, key: object) -> None:
        self.key = key


def build_service(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ClerkAuthService, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    service = ClerkAuthService(
        issuer_url="https://clerk.example.test",
        jwks_url="https://clerk.example.test/.well-known/jwks.json",
        secret_key="sk_test_example",
        authorized_parties=("https://app.example.test",),
        audience="vireal-api",
    )
    monkeypatch.setattr(
        service.jwks_client,
        "get_signing_key_from_jwt",
        lambda _token: StaticSigningKey(private_key.public_key()),
    )
    return service, private_key


def encode_token(
    private_key: object, *, kid: str = "key-one", **overrides: object
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
