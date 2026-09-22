import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import settings

AuthProvider = Literal["email", "google", "apple"]


class ClerkAuthenticationError(RuntimeError):
    pass


class ClerkAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClerkSessionClaims:
    issuer: str
    subject: str
    session_id: str
    authorized_party: str


@dataclass(frozen=True)
class ClerkUserProfile:
    primary_email: str
    email_verified: bool
    providers: tuple[AuthProvider, ...]

    def providers_json(self) -> str:
        return json.dumps(list(self.providers), separators=(",", ":"))


class ClerkAuthService:
    def __init__(
        self,
        *,
        issuer_url: str,
        jwks_url: str,
        secret_key: str,
        authorized_parties: tuple[str, ...],
        audience: str,
        api_base_url: str = "https://api.clerk.com/v1",
    ) -> None:
        self.issuer_url = issuer_url.rstrip("/")
        self.jwks_client = PyJWKClient(jwks_url)
        self.secret_key = secret_key
        self.authorized_parties = tuple(
            origin.rstrip("/") for origin in authorized_parties
        )
        self.audience = audience
        self.api_base_url = api_base_url.rstrip("/")

    def verify_session_token(self, token: str) -> ClerkSessionClaims:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer_url,
                options={
                    "require": ["iss", "sub", "sid", "aud", "azp", "exp", "nbf"],
                },
            )
        except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
            raise ClerkAuthenticationError("Invalid or expired Clerk session") from exc

        subject = payload.get("sub")
        session_id = payload.get("sid")
        authorized_party = payload.get("azp")
        if not isinstance(subject, str) or not subject:
            raise ClerkAuthenticationError("Clerk session is missing a subject")
        if not isinstance(session_id, str) or not session_id:
            raise ClerkAuthenticationError("Clerk session is missing a session id")
        if not isinstance(authorized_party, str) or not authorized_party:
            raise ClerkAuthenticationError(
                "Clerk session is missing an authorized party"
            )
        if authorized_party.rstrip("/") not in self.authorized_parties:
            raise ClerkAuthenticationError("Clerk session has an unauthorized party")
        if payload.get("sts") == "pending":
            raise ClerkAuthenticationError("Clerk session setup is incomplete")
        return ClerkSessionClaims(
            issuer=self.issuer_url,
            subject=subject,
            session_id=session_id,
            authorized_party=authorized_party,
        )

    def get_user_profile(self, subject: str) -> ClerkUserProfile:
        payload = self._request("GET", f"/users/{subject}")
        email_addresses = payload.get("email_addresses")
        if not isinstance(email_addresses, list):
            raise ClerkAPIError("Clerk user response is missing email addresses")
        primary_email_id = payload.get("primary_email_address_id")
        primary_email: str | None = None
        email_verified = False
        for email in email_addresses:
            if not isinstance(email, dict):
                continue
            if email.get("id") != primary_email_id:
                continue
            value = email.get("email_address")
            if isinstance(value, str) and value:
                primary_email = value.strip().lower()
                verification = email.get("verification")
                email_verified = bool(
                    isinstance(verification, dict)
                    and verification.get("status") == "verified"
                )
                break
        if not primary_email:
            raise ClerkAPIError("Clerk user does not have a primary email")

        providers: set[AuthProvider] = set()
        for email in email_addresses:
            if not isinstance(email, dict):
                continue
            verification = email.get("verification")
            if not isinstance(verification, dict):
                continue
            strategy = str(verification.get("strategy") or "").lower()
            if verification.get("status") == "verified" and strategy in {
                "email_code",
                "email_link",
                "email_otp",
            }:
                providers.add("email")
        external_accounts = payload.get("external_accounts")
        if isinstance(external_accounts, list):
            for account in external_accounts:
                if not isinstance(account, dict):
                    continue
                provider = str(account.get("provider") or "").lower()
                if "google" in provider:
                    providers.add("google")
                elif "apple" in provider:
                    providers.add("apple")
        ordered = tuple(
            provider
            for provider in ("email", "google", "apple")
            if provider in providers
        )
        return ClerkUserProfile(
            primary_email=primary_email,
            email_verified=email_verified,
            providers=ordered,
        )

    def revoke_user_sessions(self, subject: str) -> int:
        payload = self._request(
            "GET",
            "/sessions",
            params={"user_id": subject, "status": "active", "limit": "100"},
        )
        sessions = payload if isinstance(payload, list) else payload.get("data", [])
        revoked = 0
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_id = session.get("id")
            if not isinstance(session_id, str) or not session_id:
                continue
            self._request("POST", f"/sessions/{session_id}/revoke")
            revoked += 1
        return revoked

    def revoke_session(self, session_id: str) -> None:
        self._request("POST", f"/sessions/{session_id}/revoke")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = httpx.request(
                method,
                f"{self.api_base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.secret_key}",
                    "Accept": "application/json",
                },
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ClerkAPIError("Unable to communicate with Clerk") from exc


@lru_cache
def get_clerk_auth_service() -> ClerkAuthService:
    if (
        settings.CLERK_ISSUER_URL is None
        or settings.CLERK_JWKS_URL is None
        or settings.CLERK_AUDIENCE is None
        or settings.CLERK_SECRET_KEY is None
    ):
        raise ClerkAuthenticationError("Clerk authentication is not configured")
    return ClerkAuthService(
        issuer_url=str(settings.CLERK_ISSUER_URL),
        jwks_url=str(settings.CLERK_JWKS_URL),
        secret_key=settings.CLERK_SECRET_KEY,
        authorized_parties=tuple(
            str(origin).rstrip("/") for origin in settings.CLERK_AUTHORIZED_PARTIES
        ),
        audience=settings.CLERK_AUDIENCE,
        api_base_url=str(settings.CLERK_API_BASE_URL),
    )
