"""Auth endpoints: signup, login, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import refresh_tokens, service
from app.auth.deps import get_current_user, get_db
from app.auth.tokens import create_access_token
from app.logging_config import security_logger
from app.models import Membership, Organization, User
from app.rate_limit import AUTH_LIMIT as AUTH_RATE_LIMIT
from app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- schemas -------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    org_name: str = Field(min_length=1, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    # No min_length here — don't help an attacker learn valid password shape;
    # max_length still caps bcrypt input size (DoS/truncation hygiene).
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


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
@limiter.limit(AUTH_RATE_LIMIT)
def signup(request: Request, response: Response, req: SignupRequest,
           session: Session = Depends(get_db)) -> TokenResponse:
    try:
        user, org, _m = service.signup(
            session, email=req.email, password=req.password,
            full_name=req.full_name, org_name=req.org_name,
        )
    except service.EmailAlreadyExists:
        security_logger.info("signup rejected: email already registered",
                             extra={"event": "signup_conflict", "email": req.email})
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    security_logger.info("signup succeeded", extra={
        "event": "signup_succeeded", "user_id": str(user.id), "email": user.email, "org_id": str(org.id),
    })
    return _token_for(session, user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_RATE_LIMIT)
def login(request: Request, response: Response, req: LoginRequest,
          session: Session = Depends(get_db)) -> TokenResponse:
    user = service.authenticate(session, email=req.email, password=req.password)
    if user is None:
        security_logger.warning("login failed", extra={"event": "login_failed", "email": req.email})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    security_logger.info("login succeeded",
                         extra={"event": "login_succeeded", "user_id": str(user.id), "email": user.email})
    return _token_for(session, user)


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


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(AUTH_RATE_LIMIT)
def refresh(request: Request, response: Response, req: RefreshRequest,
            session: Session = Depends(get_db)) -> RefreshResponse:
    """Exchange a refresh token for a new access + refresh token pair (rotation).

    The presented refresh token is revoked either way — a rotated token can
    never be used twice. Reuse of an already-revoked token revokes every
    session for that user (see auth/refresh_tokens.py).
    """
    try:
        new_refresh, user_id = refresh_tokens.rotate(session, req.refresh_token)
    except refresh_tokens.RefreshTokenError:
        # TokenReused (a subclass) already logged its own security event with
        # more context inside refresh_tokens.rotate() before raising.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired refresh token")
    security_logger.info("access token refreshed",
                         extra={"event": "token_refreshed", "user_id": str(user_id)})
    access = create_access_token(str(user_id))
    return RefreshResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(req: LogoutRequest, session: Session = Depends(get_db)) -> None:
    """Revoke one refresh token — ends this session/device only."""
    revoked = refresh_tokens.revoke(session, req.refresh_token)
    if revoked:
        security_logger.info("logout", extra={"event": "logout"})


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> None:
    """Revoke every refresh token for the current user — signs out all devices."""
    count = refresh_tokens.revoke_all(session, user.id)
    security_logger.info("logout-all", extra={
        "event": "logout_all", "user_id": str(user.id), "sessions_revoked": count,
    })


def _token_for(session: Session, user: User) -> TokenResponse:
    access = create_access_token(str(user.id), extra={"email": user.email})
    refresh = refresh_tokens.issue(session, user.id)
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), email=user.email)
