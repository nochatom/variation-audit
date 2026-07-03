"""Organization invitations (.19a) — email-addressed, admin-created, auditable.

Replaces the old "add member by email" flow, which required the invited
email to already belong to a User (returning 404 "no user with that email"
otherwise). An Invitation row is created immediately regardless of whether
the email has an account yet; a User is only required at *acceptance* time.

Token format mirrors app/auth/refresh_tokens.py: raw token is "{id}.{secret}",
only the SHA-256 hash of the secret is ever persisted, and the id gives O(1)
lookup instead of hashing-and-scanning every row.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models import AuditLog, Invitation, Membership, MembershipRole, Organization, User


class InvitationError(Exception):
    """Base for invalid/expired/revoked/already-used invitation tokens."""


class InvalidToken(InvitationError):
    pass


class InvitationExpired(InvitationError):
    pass


class InvitationAlreadyUsed(InvitationError):
    pass


class InvitationRevoked(InvitationError):
    pass


class EmailMismatch(InvitationError):
    """The invitation's email doesn't match the acting/registering account."""


class EmailAlreadyRegistered(InvitationError):
    """register() called for an email that already has an account."""


class InvitationNotFound(Exception):
    pass


class AlreadyMember(Exception):
    """create_invitation() called for an email that's already in this org."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _encode(inv_id: uuid.UUID, secret: str) -> str:
    return f"{inv_id}.{secret}"


def _decode(raw: str) -> tuple[uuid.UUID, str] | None:
    id_str, _, secret = raw.partition(".")
    if not secret:
        return None
    try:
        return uuid.UUID(id_str), secret
    except ValueError:
        return None


def status_of(inv: Invitation) -> str:
    if inv.accepted_at is not None:
        return "accepted"
    if inv.revoked_at is not None:
        return "revoked"
    if inv.expires_at < _now():
        return "expired"
    return "pending"


def _audit(session: Session, company_id: uuid.UUID, actor_id: uuid.UUID | None,
          action: str, entity_id: uuid.UUID, after: dict | None) -> None:
    session.add(AuditLog(
        company_id=company_id, actor_user_id=actor_id,
        entity_type="invitation", entity_id=entity_id, action=action, after=after,
    ))


def _user_by_email(session: Session, email: str) -> User | None:
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def _membership(session: Session, company_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
    return session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.company_id == company_id
        )
    ).scalar_one_or_none()


def list_pending(session: Session, company_id: uuid.UUID) -> list[Invitation]:
    rows = session.execute(
        select(Invitation).where(
            Invitation.company_id == company_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        ).order_by(Invitation.created_at.desc())
    ).scalars().all()
    return list(rows)


def create_invitation(session: Session, *, company_id: uuid.UUID, actor: User,
                      email: str, role: MembershipRole = MembershipRole.member,
                      expire_days: int = 7) -> tuple[Invitation, str]:
    """Create (or resend/refresh) a pending invitation. Never requires the
    email to already have an account — that's the whole point of this flow.

    If the email already belongs to a member of this org, refuses (nothing to
    invite). If a pending invitation for this email already exists, it is
    revoked and replaced (resend semantics), matching GitHub/Linear/Slack.
    """
    existing_user = _user_by_email(session, email)
    if existing_user is not None:
        m = _membership(session, company_id, existing_user.id)
        if m is not None:
            raise AlreadyMember(email)

    stale = session.execute(
        select(Invitation).where(
            Invitation.company_id == company_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ).scalars().all()
    now = _now()
    for row in stale:
        row.revoked_at = now

    secret = secrets.token_urlsafe(32)
    inv = Invitation(
        id=uuid.uuid4(),
        company_id=company_id,
        email=email,
        role=role,
        token_hash=_hash(secret),
        invited_by=actor.id,
        expires_at=now + timedelta(days=expire_days),
    )
    session.add(inv)
    _audit(session, company_id, actor.id, "invitation.created", inv.id,
           {"email": email, "role": role.value})
    session.commit()
    return inv, _encode(inv.id, secret)


def revoke_invitation(session: Session, *, company_id: uuid.UUID, actor: User,
                      invitation_id: uuid.UUID) -> None:
    inv = session.get(Invitation, invitation_id)
    if inv is None or inv.company_id != company_id:
        raise InvitationNotFound(str(invitation_id))
    if status_of(inv) != "pending":
        raise InvitationError(f"invitation is {status_of(inv)}, not pending")
    inv.revoked_at = _now()
    _audit(session, company_id, actor.id, "invitation.revoked", inv.id, None)
    session.commit()


def get_invitation_by_token(session: Session, raw_token: str) -> Invitation:
    decoded = _decode(raw_token)
    if decoded is None:
        raise InvalidToken("malformed invitation token")
    inv_id, secret = decoded
    inv = session.get(Invitation, inv_id)
    if inv is None or inv.token_hash != _hash(secret):
        raise InvalidToken("unknown invitation token")
    st = status_of(inv)
    if st == "accepted":
        raise InvitationAlreadyUsed(str(inv.id))
    if st == "revoked":
        raise InvitationRevoked(str(inv.id))
    if st == "expired":
        raise InvitationExpired(str(inv.id))
    return inv


def preview(session: Session, raw_token: str) -> dict:
    """Public, pre-auth lookup for the accept-invite page: enough to render
    the right UI (login-then-accept vs register-and-accept) without exposing
    anything beyond what the invited email is already entitled to know."""
    inv = get_invitation_by_token(session, raw_token)
    org = get_organization(session, inv.company_id)
    return {
        "email": inv.email,
        "org_name": org.name if org else "",
        "role": inv.role.value,
        "account_exists": _user_by_email(session, inv.email) is not None,
    }


def get_organization(session: Session, company_id: uuid.UUID) -> Organization | None:
    return session.execute(
        select(Organization).where(Organization.id == company_id)
    ).scalar_one_or_none()


def accept_for_existing_user(session: Session, *, raw_token: str, user: User) -> Membership:
    """Accept as an already-authenticated user. Idempotent: accepting an
    invitation you're already a member under just confirms it rather than
    erroring, matching common SaaS behaviour."""
    inv = get_invitation_by_token(session, raw_token)
    if inv.email.lower() != user.email.lower():
        raise EmailMismatch(f"invitation is for {inv.email}, not {user.email}")

    existing = _membership(session, inv.company_id, user.id)
    if existing is not None:
        inv.accepted_at = _now()
        inv.accepted_by = user.id
        _audit(session, inv.company_id, user.id, "invitation.accepted", inv.id, None)
        session.commit()
        return existing

    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=inv.company_id, role=inv.role)
    session.add(membership)
    inv.accepted_at = _now()
    inv.accepted_by = user.id
    _audit(session, inv.company_id, user.id, "invitation.accepted", inv.id, {"role": inv.role.value})
    session.commit()
    return membership


def register_and_accept(session: Session, *, raw_token: str, password: str,
                        full_name: str | None) -> tuple[User, Membership]:
    """Accept by creating a brand-new account for the invited email (no
    separate org_name/signup step — the org comes from the invitation)."""
    inv = get_invitation_by_token(session, raw_token)
    if _user_by_email(session, inv.email) is not None:
        raise EmailAlreadyRegistered(inv.email)

    user = User(
        id=uuid.uuid4(),
        email=inv.email,
        full_name=full_name,
        password_hash=hash_password(password),
    )
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=inv.company_id, role=inv.role)
    session.add(user)
    session.add(membership)
    # AuditLog.actor_user_id has no ORM relationship() to User (unlike
    # Membership.user), so the unit-of-work insert-ordering can't infer that
    # this brand-new user row must land before the audit row referencing it
    # via FK — force it explicitly.
    session.flush()
    inv.accepted_at = _now()
    inv.accepted_by = user.id
    _audit(session, inv.company_id, user.id, "invitation.accepted", inv.id,
           {"role": inv.role.value, "via": "register"})
    session.commit()
    return user, membership
