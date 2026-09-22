import pytest
from fastapi.testclient import TestClient

from app.api import deps as deps_module
from app.core.config import settings
from app.services.cloudflare_access import CloudflareAccessError

pytestmark = pytest.mark.usefixtures("required_cloudflare_access")


class FakeAccessVerifier:
    def verify(self, token: str) -> dict[str, object]:
        if token != "valid-access-assertion":
            raise CloudflareAccessError("invalid")
        return {"sub": "admin@example.com"}


@pytest.fixture
def required_cloudflare_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCESS_REQUIRED", True)
    monkeypatch.setattr(
        deps_module,
        "get_cloudflare_access_verifier",
        lambda: FakeAccessVerifier(),
    )


def test_admin_route_requires_cloudflare_access_assertion(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/users",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cloudflare Access is required"


def test_admin_route_accepts_valid_cloudflare_access_assertion(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/users",
        headers={
            **superuser_token_headers,
            "Cf-Access-Jwt-Assertion": "valid-access-assertion",
        },
    )

    assert response.status_code == 200


def test_admin_route_rejects_invalid_cloudflare_access_assertion(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/admin/app/users",
        headers={
            **superuser_token_headers,
            "Cf-Access-Jwt-Assertion": "invalid-access-assertion",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid Cloudflare Access session"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/login/access-token"),
        ("get", "/users/me"),
        ("get", "/items/"),
    ],
)
def test_legacy_admin_routes_cannot_bypass_cloudflare_access(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    method: str,
    path: str,
) -> None:
    response = client.request(
        method,
        f"{settings.API_V1_STR}{path}",
        headers=superuser_token_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cloudflare Access is required"
