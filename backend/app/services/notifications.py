"""Notifications service (.18) — user-scoped read/unread management.

The worker writes Notification rows (analysis_complete / analysis_failed); this
exposes them to the user who triggered the work. Notifications are scoped to the
recipient user, not just the org.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def list_for_user(session: Session, user: User, *, unread_only: bool = False,
                  limit: int = 50) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def unread_count(session: Session, user: User) -> int:
    rows = session.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).scalars().all()
    return len(list(rows))


def mark_read(session: Session, user: User, notification_id: uuid.UUID) -> Notification | None:
    n = session.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    ).scalar_one_or_none()
    if n is None:
        return None
    if n.read_at is None:
        n.read_at = _now()
        session.commit()
    return n


def mark_all_read(session: Session, user: User) -> int:
    unread = session.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).scalars().all()
    now = _now()
    for n in unread:
        n.read_at = now
    if unread:
        session.commit()
    return len(list(unread))
