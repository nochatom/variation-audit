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

    # Robustly resolve email_verified: check the top-level claim, and fall back
    # to the nested user_metadata field (standard for social/OAuth providers
    # like Google under Supabase GoTrue), failing closed to False if neither is set.
    email_verified = payload.get("email_verified")
    if email_verified is None:
        user_metadata = payload.get("user_metadata") or {}
        email_verified = user_metadata.get("email_verified")

    if email_verified is None:
        email_verified = False

    return SupabaseClaims(
        sub=sub,
        email=email,
        email_verified=bool(email_verified),
    )
