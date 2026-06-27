"""JWT access tokens (HS256)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings


class TokenError(Exception):
    """Invalid, expired, or malformed token."""


def create_access_token(subject: str, *, extra: dict | None = None,
                        expires_minutes: int | None = None) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes or s.access_token_expire_minutes)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
