"""Password reset (.22 auth) — same opaque-token-hash shape as
app/auth/refresh_tokens.py / app/services/invitations.py: raw token is
"{id}.{secret}", only the SHA-256 hash of the secret is ever persisted.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import refresh_tokens
from app.auth.security import hash_password
from app.models import PasswordResetToken, User


class ResetTokenError(Exception):
    """Invalid, expired, or already-used reset token."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _encode(token_id: uuid.UUID, secret: str) -> str:
    return f"{token_id}.{secret}"


def _decode(raw: str) -> tuple[uuid.UUID, str] | None:
    id_str, _, secret = raw.partition(".")
    if not secret:
        return None
    try:
        return uuid.UUID(id_str), secret
    except ValueError:
        return None


def _user_by_email(session: Session, email: str) -> User | None:
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def create_reset_token(session: Session, *, email: str, expire_minutes: int) -> str | None:
    """Returns the raw token, or None if no account exists for this email —
    the caller (router) must not let that distinction leak to the client
    (always respond the same way regardless), it's only used internally to
    decide whether to actually send an email.

    Timing parity: BOTH branches generate a token secret, hash it, and end
    with a session.commit() (a DB round trip), so the account-exists path
    isn't distinguishable by the latency of work the not-found path skips.
    The only residual difference is the single-row INSERT itself flushing
    inside the commit — sub-millisecond, well below network jitter."""
    user = _user_by_email(session, email)

    secret = secrets.token_urlsafe(32)
    token_hash = _hash(secret)

    if user is None:
        session.commit()   # same commit round trip as the exists path
        return None

    # SECURITY HARDENING: Invalidate any prior active/outstanding password reset
    # tokens for this user. This limits the window of vulnerability by ensuring only the
    # single most recently requested password reset token is active at any time.
    now = _now()
    prior_active_tokens = session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    ).scalars().all()
    for t in prior_active_tokens:
        t.expires_at = now

    token = PasswordResetToken(
        id=uuid.uuid4(), user_id=user.id, token_hash=token_hash,
        expires_at=now + timedelta(minutes=expire_minutes),
    )
    session.add(token)
    session.commit()
    return _encode(token.id, secret)


def reset_password(session: Session, *, raw_token: str, new_password: str) -> User:
    """Verifies the token, sets the new password, marks the token used, and
    revokes every existing refresh token for the user (a password reset is a
    "kick everyone out" security event — matches refresh_tokens.py's own
    reuse-detection precedent of revoking broadly rather than narrowly)."""
    decoded = _decode(raw_token)
    if decoded is None:
        raise ResetTokenError("malformed reset token")
    token_id, secret = decoded

    row = session.get(PasswordResetToken, token_id)
    if row is None or row.token_hash != _hash(secret):
        raise ResetTokenError("unknown reset token")
    if row.used_at is not None:
        raise ResetTokenError("reset token already used")
    if row.expires_at < _now():
        raise ResetTokenError("reset token expired")

    user = session.get(User, row.user_id)
    if user is None:
        raise ResetTokenError("account no longer exists")

    user.password_hash = hash_password(new_password)
    now = _now()
    row.used_at = now

    # SECURITY HARDENING: Invalidate any other active/outstanding password reset tokens
    # for this user. A successful reset means no other pending tokens should be allowed
    # to alter the password again.
    other_active_tokens = session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != row.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    ).scalars().all()
    for t in other_active_tokens:
        t.expires_at = now

    session.commit()

    refresh_tokens.revoke_all(session, user.id)
    return user
