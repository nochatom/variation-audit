"""FastAPI auth dependencies — resolve the current user + org memberships."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import TokenError, decode_token
from app.db import session_factory
from app.models import Membership, MembershipRole, User

_bearer = HTTPBearer(auto_error=True)


def get_db():
    with session_factory() as session:
        yield session


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    session: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(creds.credentials)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    sub = payload.get("sub")
    try:
        user = session.get(User, uuid.UUID(sub)) if sub else None
    except ValueError:
        # A signed token whose sub isn't a UUID is still an invalid credential —
        # answer 401, never a 500.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


def get_memberships(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Membership]:
    return list(session.execute(
        select(Membership).where(Membership.user_id == user.id)
    ).scalars().all())


def ensure_member(session: Session, user: User, company_id: uuid.UUID) -> Membership:
    """Org isolation guard — 403 unless `user` belongs to `company_id`."""
    m = session.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.company_id == company_id
        )
    ).scalar_one_or_none()
    if m is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this organization")
    return m


def require_admin(session: Session, user: User, company_id: uuid.UUID) -> Membership:
    """RBAC guard — 403 unless `user` is an admin of `company_id`."""
    m = ensure_member(session, user, company_id)
    if m.role != MembershipRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return m


def require_any_org_admin(
    user: User = Depends(get_current_user), session: Session = Depends(get_db),
) -> User:
    """Admin of at least one organization — for platform-wide diagnostics
    endpoints (e.g. /internal/providers, /internal/storage) where the data
    isn't scoped to any single org, so the usual org-scoped require_admin
    doesn't fit. This codebase has no separate "platform admin" role;
    requiring org-admin-of-any-org is the closest fit to "the existing admin
    authorization mechanism" without inventing a new one.

    Hardened: uses .limit(1) before .scalar_one_or_none() to prevent MultipleResultsFound
    errors when a user is an admin of multiple organizations.
    """
    is_admin = session.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.role == MembershipRole.admin,
        ).limit(1)
    ).scalar_one_or_none()
    if is_admin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return user
