"""Verifies Supabase-issued access tokens via JWKS (Google login only).

This is deliberately separate from app/auth/tokens.py's HS256
create_access_token/decode_token, which mint and verify THIS app's own
session tokens and are untouched by this module. A Supabase token is only
ever exchanged (via POST /auth/google) for this app's own token pair — it is
never accepted as a session credential on any other endpoint.

Verification is local (no per-request call to Supabase's servers): PyJWT's
PyJWKClient fetches and caches Supabase's public signing keys from the
project's well-known JWKS endpoint, matched by `kid` in the token header.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.auth.tokens import TokenError
from app.config import get_settings
from app.logging_config import security_logger


class SupabaseNotConfigured(Exception):
    """VA_SUPABASE_URL is unset — Google login via Supabase isn't available."""


@dataclass(frozen=True)
class SupabaseClaims:
    sub: str
    email: str
    email_verified: bool


@lru_cache
def _jwks_client(supabase_url: str) -> PyJWKClient:
    # Cached per supabase_url (effectively a singleton — settings don't
    # change at runtime), so PyJWKClient's own key-set cache persists across
    # requests within the process, not just within a single call.
    return PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def verify_supabase_token(token: str) -> SupabaseClaims:
    settings = get_settings()
    if not settings.supabase_url:
        raise SupabaseNotConfigured("VA_SUPABASE_URL is not set")

    try:
        signing_key = _jwks_client(settings.supabase_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token, signing_key.key, algorithms=["ES256", "RS256"],
            audience=settings.supabase_jwt_aud,
            # Pin the issuer to OUR Supabase project — a validly-signed token
            # must also have been minted by this project's auth server, and a
            # token with no iss claim at all is rejected outright.
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
            options={"require": ["iss"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not email:
        raise TokenError("Supabase token missing sub/email claim")

    # TEMPORARY diagnostic (.27 investigation): log the claim shape (keys +
    # user_metadata keys only, never values — this can contain PII) so we
    # can see exactly where Google-OAuth logins carry email_verified. Remove
    # once the real claim path is confirmed and hardcoded below.
    security_logger.info("supabase token claim shape (diagnostic)", extra={
        "event": "supabase_claim_shape_diagnostic",
        "top_level_keys": sorted(payload.keys()),
        "user_metadata_keys": sorted((payload.get("user_metadata") or {}).keys()),
        "app_metadata_keys": sorted((payload.get("app_metadata") or {}).keys()),
        "top_level_email_verified": payload.get("email_verified"),
        "user_metadata_email_verified": (payload.get("user_metadata") or {}).get("email_verified"),
        "provider": (payload.get("app_metadata") or {}).get("provider"),
    })

    return SupabaseClaims(
        sub=sub, email=email,
        # Fail closed: a token without an explicit email_verified claim is
        # treated as UNVERIFIED. Supabase always emits this claim for both
        # password and OAuth users, so a legitimate token never hits the
        # default — only a malformed/unexpected one does, and that must not
        # be allowed to link into an existing account by email.
        email_verified=payload.get("email_verified", False),
    )
