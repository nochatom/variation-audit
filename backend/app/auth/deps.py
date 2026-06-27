"""FastAPI auth dependencies — resolve the current user + org memberships."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import TokenError, decode_token
from app.db import session_factory
from app.models import Membership, User

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
    user = session.get(User, uuid.UUID(sub)) if sub else None
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
