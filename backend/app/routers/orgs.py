"""Organization member-management endpoints (.19) — admin-only."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db, require_admin
from app.models import MembershipRole, User
from app.services import orgs as org_service

router = APIRouter(prefix="/orgs/{company_id}/members", tags=["organizations"])


class MemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str | None = None
    role: str


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.member


class RoleUpdate(BaseModel):
    role: MembershipRole


@router.get("", response_model=list[MemberOut])
def list_members(company_id: uuid.UUID, user: User = Depends(get_current_user),
                 session: Session = Depends(get_db)) -> list[MemberOut]:
    require_admin(session, user, company_id)
    return [
        MemberOut(user_id=str(u.id), email=u.email, full_name=u.full_name, role=m.role.value)
        for m, u in org_service.list_members(session, company_id)
    ]


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(company_id: uuid.UUID, req: AddMemberRequest,
               user: User = Depends(get_current_user),
               session: Session = Depends(get_db)) -> MemberOut:
    require_admin(session, user, company_id)
    try:
        m = org_service.add_member(session, company_id=company_id, actor=user,
                                   email=req.email, role=req.role)
    except org_service.UserNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no user with that email")
    except org_service.AlreadyMember:
        raise HTTPException(status.HTTP_409_CONFLICT, "already a member")
    return MemberOut(user_id=str(m.user_id), email=req.email, role=m.role.value)


@router.patch("/{target_user_id}", response_model=MemberOut)
def update_role(company_id: uuid.UUID, target_user_id: uuid.UUID, req: RoleUpdate,
                user: User = Depends(get_current_user),
                session: Session = Depends(get_db)) -> MemberOut:
    require_admin(session, user, company_id)
    try:
        m = org_service.set_role(session, company_id=company_id, actor=user,
                                 target_user_id=target_user_id, role=req.role)
    except org_service.NotAMember:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")
    except org_service.LastAdmin:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot demote the last admin")
    return MemberOut(user_id=str(target_user_id), email="", role=m.role.value)


@router.delete("/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(company_id: uuid.UUID, target_user_id: uuid.UUID,
                  user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> None:
    require_admin(session, user, company_id)
    try:
        org_service.remove_member(session, company_id=company_id, actor=user,
                                  target_user_id=target_user_id)
    except org_service.NotAMember:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a member")
    except org_service.LastAdmin:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot remove the last admin")
