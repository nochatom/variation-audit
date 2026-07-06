"""Google-login-via-Supabase account resolution (.25).

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
from app.services import invitations as invitations_service


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
    - No matching account, but a pending Invitation exists for this email:
      the new User joins the inviting org(s) instead of getting a stray new
      Organization — the same outcome as using the invitation link, just
      via a different front door (see
      services/invitations.py:accept_pending_invitations_for_email).
    - No matching account and no pending invitation: a brand-new User
      (password_hash=None — Google owns this identity's credentials) +
      Organization + admin Membership are created together, mirroring
      service.signup()'s shape, so a first-time Google user lands in a
      usable org exactly like a first-time email/password signup does.
    """
    if not claims.email_verified:
        raise UnverifiedEmail(claims.email)

    existing = _user_by_email(session, claims.email)
    if existing is not None:
        return existing, False

    user = User(id=uuid.uuid4(), email=claims.email, full_name=None, password_hash=None)
    session.add(user)
    # No ORM relationship links Invitation/Membership rows to this brand-new
    # User by Python object identity (unlike Organization/Membership below,
    # which SQLAlchemy can order via the relationship) — flush so user.id is
    # a valid FK target before accept_pending_invitations_for_email inserts
    # against it. Same reasoning as invitations.py:register_and_accept.
    session.flush()

    memberships = invitations_service.accept_pending_invitations_for_email(
        session, user=user, email=claims.email, via="google",
    )
    if not memberships:
        org = Organization(id=uuid.uuid4(), name=f"{claims.email.split('@')[0]}'s Organization")
        membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=org.id, role=MembershipRole.admin)
        session.add(org)
        session.add(membership)
        session.commit()
    return user, True
