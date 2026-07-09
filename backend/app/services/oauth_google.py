"""Google-login-via-Supabase account resolution.

Adds Google as a login *method* only — it never introduces a parallel
session type. A verified Supabase identity is resolved to this app's own
`User` row (matched by email, or created if none exists) exactly the way
`app/auth/service.py:signup()` already does for email/password, then the
existing `_token_for()` helper in app/auth/router.py mints this app's usual
access+refresh token pair. Existing signup/login/refresh and all RBAC logic
are untouched.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.supabase_jwt import SupabaseClaims
from app.models import Membership, MembershipRole, Organization, User


class UnverifiedEmail(Exception):
    """The Supabase token's email isn't marked verified — refuse to link or
    create an account against it (would otherwise let an attacker with an
    unverified-email OAuth identity match/access someone else's existing
    password-based account by claiming their email)."""


def _user_by_email(session: Session, email: str) -> User | None:
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def login_or_signup_with_google(session: Session, claims: SupabaseClaims) -> tuple[User, bool]:
    """Returns (user, is_new_user).

    - An existing local account with a matching (verified) email logs in as
      that account — password-based and Google-based sign-in resolve to the
      same User/Membership rows.
    - No matching account: a brand-new User (password_hash=None — Google
      owns this identity's credentials) + Organization + admin Membership
      are created together, mirroring service.signup()'s shape, so a
      first-time Google user lands in a usable org exactly like a first-time
      email/password signup does.
    """
    if not claims.email_verified:
        raise UnverifiedEmail(claims.email)

    existing = _user_by_email(session, claims.email)
    if existing is not None:
        return existing, False

    org = Organization(id=uuid.uuid4(), name=f"{claims.email.split('@')[0]}'s Organization")
    user = User(id=uuid.uuid4(), email=claims.email, full_name=None, password_hash=None)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=org.id, role=MembershipRole.admin)
    session.add(org)
    session.add(user)
    session.add(membership)
    session.commit()
    return user, True
