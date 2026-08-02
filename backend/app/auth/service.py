"""Auth service — signup and authentication.

Signup is multi-tenant: it creates an Organization, the User, and an admin
Membership linking them. IDs are minted explicitly so the FK links are valid
regardless of flush timing (and unit-testable without a live DB).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.models import Membership, MembershipRole, Organization, User


class EmailAlreadyExists(Exception):
    pass


def _user_by_email(session: Session, email: str) -> User | None:
    return session.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()


def signup(session: Session, *, email: str, password: str,
           full_name: str | None, org_name: str) -> tuple[User, Organization, Membership]:
    if _user_by_email(session, email) is not None:
        raise EmailAlreadyExists(email)

    org = Organization(id=uuid.uuid4(), name=org_name)
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
    )
    membership = Membership(
        id=uuid.uuid4(),
        user_id=user.id,
        company_id=org.id,
        role=MembershipRole.admin,   # first user owns the org
    )
    session.add(org)
    session.add(user)
    session.add(membership)
    session.commit()
    return user, org, membership


def authenticate(session: Session, *, email: str, password: str) -> User | None:
    # A dummy bcrypt hash of "dummy" with cost factor 10 to ensure timing parity
    # when the user is not found, inactive, or has no local password hash.
    # Cost factor 10 matches _BCRYPT_ROUNDS in app/auth/security.py.
    dummy_hash = "$2b$10$ExEKaj3Sm7ZjDeOIWbDWROKaSGAP5uyeuokkEdv.42931vdp1jtty"

    user = _user_by_email(session, email)

    if user is not None and user.is_active and user.password_hash is not None:
        if verify_password(password, user.password_hash):
            return user
        return None
    else:
        # Perform a dummy password verification to prevent timing-based user enumeration
        # and timing leaks across the failure branches.
        verify_password(password, dummy_hash)
        return None
