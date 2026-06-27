"""Organization member management (.19) — admin-only, audited, lockout-safe.

Adds/removes members and changes roles within an org. Guards against removing
or demoting the last admin (which would lock everyone out of management).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Membership, MembershipRole, Organization, User


class UserNotFound(Exception):
    pass


class AlreadyMember(Exception):
    pass


class NotAMember(Exception):
    pass


class LastAdmin(Exception):
    """Refusing an action that would leave the org with no admin."""


def _admins(session: Session, company_id: uuid.UUID) -> list[Membership]:
    return list(session.execute(
        select(Membership).where(
            Membership.company_id == company_id,
            Membership.role == MembershipRole.admin,
        )
    ).scalars().all())


def list_members(session: Session, company_id: uuid.UUID) -> list[tuple[Membership, User]]:
    rows = session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.company_id == company_id)
    ).all()
    return [(m, u) for m, u in rows]


def add_member(session: Session, *, company_id: uuid.UUID, actor: User,
               email: str, role: MembershipRole = MembershipRole.member) -> Membership:
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise UserNotFound(email)
    existing = session.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.company_id == company_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AlreadyMember(email)

    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=company_id, role=role)
    session.add(membership)
    _audit(session, company_id, actor, "member.added", user.id, {"role": role.value})
    session.commit()
    return membership


def set_role(session: Session, *, company_id: uuid.UUID, actor: User,
             target_user_id: uuid.UUID, role: MembershipRole) -> Membership:
    m = _membership(session, company_id, target_user_id)
    if m.role == MembershipRole.admin and role != MembershipRole.admin and len(_admins(session, company_id)) <= 1:
        raise LastAdmin(str(target_user_id))
    before = m.role.value
    m.role = role
    _audit(session, company_id, actor, "member.role_changed", target_user_id,
           {"from": before, "to": role.value})
    session.commit()
    return m


def remove_member(session: Session, *, company_id: uuid.UUID, actor: User,
                  target_user_id: uuid.UUID) -> None:
    m = _membership(session, company_id, target_user_id)
    if m.role == MembershipRole.admin and len(_admins(session, company_id)) <= 1:
        raise LastAdmin(str(target_user_id))
    session.delete(m)
    _audit(session, company_id, actor, "member.removed", target_user_id, None)
    session.commit()


def _membership(session: Session, company_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    m = session.execute(
        select(Membership).where(
            Membership.user_id == user_id, Membership.company_id == company_id
        )
    ).scalar_one_or_none()
    if m is None:
        raise NotAMember(str(user_id))
    return m


def _audit(session: Session, company_id, actor: User, action: str,
           target_user_id: uuid.UUID, after: dict | None) -> None:
    session.add(AuditLog(
        company_id=company_id, actor_user_id=actor.id,
        entity_type="membership", entity_id=target_user_id, action=action, after=after,
    ))
