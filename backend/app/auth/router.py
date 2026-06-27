"""Auth endpoints: signup, login, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.deps import get_current_user, get_db
from app.auth.tokens import create_access_token
from app.models import Membership, Organization, User

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- schemas -------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    org_name: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class OrgOut(BaseModel):
    id: str
    name: str
    role: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    full_name: str | None = None
    organizations: list[OrgOut] = []


# ---- endpoints -----------------------------------------------------------
@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, session: Session = Depends(get_db)) -> TokenResponse:
    try:
        user, _org, _m = service.signup(
            session, email=req.email, password=req.password,
            full_name=req.full_name, org_name=req.org_name,
        )
    except service.EmailAlreadyExists:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    return _token_for(user)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, session: Session = Depends(get_db)) -> TokenResponse:
    user = service.authenticate(session, email=req.email, password=req.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return _token_for(user)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> MeResponse:
    rows = session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.company_id)
        .where(Membership.user_id == user.id)
    ).all()
    orgs = [OrgOut(id=str(o.id), name=o.name, role=m.role.value) for m, o in rows]
    return MeResponse(user_id=str(user.id), email=user.email,
                      full_name=user.full_name, organizations=orgs)


def _token_for(user: User) -> TokenResponse:
    token = create_access_token(str(user.id), extra={"email": user.email})
    return TokenResponse(access_token=token, user_id=str(user.id), email=user.email)
