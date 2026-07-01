"""Rotating, revocable refresh tokens (.2.1).

Raw token format: "{row_id}.{secret}" — the row id lets lookup be O(1) by
primary key instead of hashing-and-scanning every stored token; the secret
(32 random bytes, URL-safe) is what's actually verified via SHA-256 hash
comparison against the stored token_hash. Only the hash is ever persisted.

Rotation: every successful refresh revokes the presented token and issues a
brand new one (never re-extend the same row). If an already-revoked token is
presented again, that means a token was used twice — a strong signal of theft
(e.g. a stolen refresh token used by both the attacker and the legitimate
user) — so ALL of that user's refresh tokens are revoked as a precaution.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import security_logger
from app.models import RefreshToken


class RefreshTokenError(Exception):
    """Base for invalid/expired/revoked refresh token presentations."""


class TokenReused(RefreshTokenError):
    """An already-rotated (revoked) token was presented again — likely theft.

    All of the token's user's refresh tokens have already been revoked by the
    time this is raised, forcing every session to re-authenticate.
    """


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _encode(token_id: uuid.UUID, secret: str) -> str:
    return f"{token_id}.{secret}"


def _decode(raw: str) -> tuple[uuid.UUID, str] | None:
    token_id_str, _, secret = raw.partition(".")
    if not secret:
        return None
    try:
        return uuid.UUID(token_id_str), secret
    except ValueError:
        return None


def issue(session: Session, user_id: uuid.UUID) -> str:
    """Create a new refresh token row and return the raw token to hand the client."""
    secret = secrets.token_urlsafe(32)
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=_hash(secret),
        expires_at=_now() + timedelta(days=get_settings().refresh_token_expire_days),
    )
    session.add(row)
    session.commit()
    return _encode(row.id, secret)


def rotate(session: Session, raw_token: str) -> tuple[str, uuid.UUID]:
    """Validate raw_token, revoke it, and issue+return a replacement.

    Raises RefreshTokenError (or TokenReused) if raw_token is malformed,
    unknown, expired, or already revoked.
    """
    decoded = _decode(raw_token)
    if decoded is None:
        raise RefreshTokenError("malformed refresh token")
    token_id, secret = decoded

    row = session.get(RefreshToken, token_id)
    if row is None or row.token_hash != _hash(secret):
        raise RefreshTokenError("unknown refresh token")

    if row.revoked_at is not None:
        # Reuse of an already-rotated token — treat as compromised and kill
        # every session for this user, not just this one token.
        revoked_count = revoke_all(session, row.user_id)
        security_logger.warning(
            "refresh token reuse detected; all sessions revoked",
            extra={
                "event": "refresh_token_reuse_detected",
                "user_id": str(row.user_id),
                "token_id": str(row.id),
                "sessions_revoked": revoked_count,
            },
        )
        raise TokenReused("refresh token reuse detected; all sessions revoked")

    if row.expires_at < _now():
        raise RefreshTokenError("refresh token expired")

    new_raw = issue(session, row.user_id)
    new_id, _ = _decode(new_raw)  # type: ignore[misc]
    row.revoked_at = _now()
    row.replaced_by_id = new_id
    session.commit()
    return new_raw, row.user_id


def revoke(session: Session, raw_token: str) -> bool:
    """Revoke a single refresh token (logout). Returns False if not found/already revoked."""
    decoded = _decode(raw_token)
    if decoded is None:
        return False
    token_id, secret = decoded
    row = session.get(RefreshToken, token_id)
    if row is None or row.token_hash != _hash(secret) or row.revoked_at is not None:
        return False
    row.revoked_at = _now()
    session.commit()
    return True


def revoke_all(session: Session, user_id: uuid.UUID) -> int:
    """Revoke every active refresh token for a user (logout-all / suspected compromise)."""
    active = session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    ).scalars().all()
    now = _now()
    for row in active:
        row.revoked_at = now
    if active:
        session.commit()
    return len(active)
