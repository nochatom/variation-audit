"""Notification endpoints (.18) — user-scoped."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db
from app.models import User
from app.services import notifications as notif_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    type: str
    payload: dict
    read: bool
    created_at: str


def _out(n) -> NotificationOut:
    return NotificationOut(
        id=str(n.id), type=n.type, payload=n.payload or {},
        read=n.read_at is not None,
        created_at=n.created_at.isoformat() if n.created_at else "",
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(unread: bool = False,
                       # Clamped: an attacker-controlled limit must not be able
                       # to force an arbitrarily large result set into memory.
                       limit: int = Query(50, ge=1, le=200),
                       user: User = Depends(get_current_user),
                       session: Session = Depends(get_db)) -> list[NotificationOut]:
    rows = notif_service.list_for_user(session, user, unread_only=unread, limit=limit)
    return [_out(n) for n in rows]


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user),
                 session: Session = Depends(get_db)) -> dict:
    return {"count": notif_service.unread_count(session, user)}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, user: User = Depends(get_current_user),
              session: Session = Depends(get_db)) -> NotificationOut:
    n = notif_service.mark_read(session, user, notification_id)
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    return _out(n)


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> dict:
    return {"marked": notif_service.mark_all_read(session, user)}
