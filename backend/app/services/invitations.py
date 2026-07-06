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
from sqlalchemy.exc import IntegrityError
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


class DuplicateInvitation(Exception):
    """A non-expired pending invitation for this (company, email) already exists."""


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
    """Create a pending invitation. Never requires the email to already have
    an account — that's the whole point of this flow.

    Refuses (AlreadyMember) if the email already belongs to a member of this
    org. Refuses (DuplicateInvitation) if a still-pending (non-expired)
    invitation for this email already exists — the admin must revoke it
    first (DELETE .../invitations/{id}) before re-inviting, rather than this
    silently resending. A merely *expired* dangling invitation does NOT
    block re-inviting: it's auto-revoked here so the email is never
    permanently stuck just because a 7-day-old invite lapsed.

    A DB-level partial unique index (company_id, email WHERE accepted_at IS
    NULL AND revoked_at IS NULL — migration 0005) backstops this against a
    race between two concurrent invites for the same email; a violation of
    that index is caught below and re-raised as DuplicateInvitation too.
    """
    existing_user = _user_by_email(session, email)
    if existing_user is not None:
        m = _membership(session, company_id, existing_user.id)
        if m is not None:
            raise AlreadyMember(email)

    now = _now()
    open_rows = session.execute(
        select(Invitation).where(
            Invitation.company_id == company_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ).scalars().all()
    for row in open_rows:
        if row.expires_at < now:
            row.revoked_at = now
        else:
            raise DuplicateInvitation(email)

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
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DuplicateInvitation(email) from None
    return inv, _encode(inv.id, secret)


def revoke_invitation(session: Session, *, company_id: uuid.UUID, actor: User,
                      invitation_id: uuid.UUID) -> None:
    """Revoke a pending OR expired invitation (both are "not yet accepted,
    still visible in the pending list" from the admin's point of view — an
    expired one must stay revocable so the admin isn't ever stuck unable to
    dismiss it or re-invite the same email). Already accepted/revoked
    invitations can't be revoked again."""
    inv = session.get(Invitation, invitation_id)
    if inv is None or inv.company_id != company_id:
        raise InvitationNotFound(str(invitation_id))
    st = status_of(inv)
    if st not in ("pending", "expired"):
        raise InvitationError(f"invitation is {st}, cannot be revoked")
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


def accept_pending_invitations_for_email(session: Session, *, user: User, email: str,
                                         via: str = "direct") -> list[Membership]:
    """Accept every still-pending invitation addressed to `email` on behalf
    of `user` (callers must already have verified `user`'s email matches —
    e.g. only after a trusted identity provider confirms it).

    Used by the Google-login path (.25): a first-time Google sign-in for an
    address that already has a pending invitation joins the inviting org(s)
    instead of getting a stray brand-new Organization — the same end state
    as using the invitation link, just via a different front door. Returns
    an empty list (no commit) if there's nothing pending, so callers can
    fall back to their own "no invitation — create a new org" logic.
    """
    now = _now()
    pending = session.execute(
        select(Invitation).where(
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at >= now,
        )
    ).scalars().all()
    if not pending:
        return []

    memberships: list[Membership] = []
    for inv in pending:
        existing = _membership(session, inv.company_id, user.id)
        if existing is not None:
            inv.accepted_at = now
            inv.accepted_by = user.id
            _audit(session, inv.company_id, user.id, "invitation.accepted", inv.id, {"via": via})
            memberships.append(existing)
            continue
        membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=inv.company_id, role=inv.role)
        session.add(membership)
        inv.accepted_at = now
        inv.accepted_by = user.id
        _audit(session, inv.company_id, user.id, "invitation.accepted", inv.id,
              {"role": inv.role.value, "via": via})
        memberships.append(membership)
    session.commit()
    return memberships


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
