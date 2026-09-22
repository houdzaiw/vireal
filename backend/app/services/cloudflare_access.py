from functools import lru_cache

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import settings


class CloudflareAccessError(RuntimeError):
    pass


class CloudflareAccessVerifier:
    def __init__(self, *, team_domain: str, audience: str) -> None:
        self.team_domain = team_domain.rstrip("/")
        self.audience = audience
        self.jwks_client = PyJWKClient(f"{self.team_domain}/cdn-cgi/access/certs")

    def verify(self, token: str) -> dict[str, object]:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.team_domain,
            )
        except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
            raise CloudflareAccessError("Invalid Cloudflare Access session") from exc


@lru_cache
def get_cloudflare_access_verifier() -> CloudflareAccessVerifier:
    if (
        settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN is None
        or settings.CLOUDFLARE_ACCESS_AUD is None
    ):
        raise CloudflareAccessError("Cloudflare Access is not configured")
    return CloudflareAccessVerifier(
        team_domain=str(settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN),
        audience=settings.CLOUDFLARE_ACCESS_AUD,
    )
