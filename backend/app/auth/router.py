"""Auth endpoints: signup, login, me."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import refresh_tokens, service
from app.auth.deps import get_current_user, get_db
from app.auth.security import hash_password
from app.auth.supabase_jwt import SupabaseNotConfigured, verify_supabase_token
from app.auth.tokens import TokenError, create_access_token
from app.config import get_settings
from app.logging_config import security_logger
from app.mailer import get_mailer
from app.models import Membership, Organization, User
from app.rate_limit import AUTH_LIMIT as AUTH_RATE_LIMIT
from app.rate_limit import limiter
from app.services import oauth_google
from app.services import password_reset as password_reset_service

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- schemas -------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    org_name: str = Field(min_length=1, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)


class SignupAccepted(BaseModel):
    # Deliberately the SAME body whether the email was new or already
    # registered — the signup response must not be a user-enumeration oracle.
    # The frontend follows up with a normal /auth/login using the same
    # credentials (succeeds for a genuinely new account; fails with the
    # generic "invalid credentials" otherwise).
    message: str


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


class GoogleLoginRequest(BaseModel):
    # An access token obtained from a Supabase client-side OAuth session
    # (supabase.auth.signInWithOAuth({provider: "google"})) — verified here
    # via JWKS, then discarded; only this app's own TokenResponse is used
    # afterward. See app/auth/supabase_jwt.py.
    supabase_access_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class OrgOut(BaseModel):
    id: str
    name: str
    role: str


class MeResponse(BaseModel):
    user_id: str
    email: str
    full_name: str | None = None
    organizations: list[OrgOut] = []


class UpdateMeRequest(BaseModel):
    # Same length bound as SignupRequest.full_name. Only the profile's
    # display name is editable here — email/password/org membership all have
    # their own dedicated, separately-authorized flows and are not touched.
    full_name: str | None = Field(default=None, max_length=200)


# ---- endpoints -----------------------------------------------------------
_SIGNUP_ACCEPTED_MESSAGE = "Account request received — signing you in."


@router.post("/signup", response_model=SignupAccepted, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(AUTH_RATE_LIMIT)
def signup(request: Request, response: Response, req: SignupRequest,
           background_tasks: BackgroundTasks,
           session: Session = Depends(get_db), mailer=Depends(get_mailer)) -> SignupAccepted:
    """Always 202 with an identical body, whether or not the email was
    already registered — the old 409 was a deterministic user-enumeration
    oracle. If the account already exists, the legitimate owner is told by
    email (sent in the background, so response timing doesn't leak it
    either); the caller just proceeds to /auth/login, which fails with the
    same generic message any wrong credential gets."""
    try:
        user, org, _m = service.signup(
            session, email=req.email, password=req.password,
            full_name=req.full_name, org_name=req.org_name,
        )
        security_logger.info("signup succeeded", extra={
            "event": "signup_succeeded", "user_id": str(user.id), "email": user.email, "org_id": str(org.id),
        })
    except service.EmailAlreadyExists:
        # Timing parity with the success path: pay the same bcrypt hash the
        # success path pays, and end with the same commit round trip
        # service.signup() performs. The residual difference (three row
        # INSERTs flushing inside that commit) is sub-millisecond — far
        # below network jitter.
        hash_password(req.password)
        session.commit()
        base = get_settings().frontend_base_url.rstrip("/")
        background_tasks.add_task(_send_best_effort, mailer.send_account_exists_notice,
                                  to_email=req.email, login_url=f"{base}/login")
        security_logger.info("signup for already-registered email — owner notified",
                             extra={"event": "signup_conflict", "email": req.email})
    return SignupAccepted(message=_SIGNUP_ACCEPTED_MESSAGE)


def _send_best_effort(send_fn, **kwargs) -> None:
    """Background email wrapper: a mail failure after the response has been
    sent must be logged, never raised into the ASGI error path."""
    try:
        send_fn(**kwargs)
    except Exception:  # noqa: BLE001
        security_logger.warning("background email send failed",
                                extra={"event": "background_email_failed"})


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


@router.post("/google", response_model=TokenResponse)
@limiter.limit(AUTH_RATE_LIMIT)
def google_login(request: Request, response: Response, req: GoogleLoginRequest,
                 session: Session = Depends(get_db)) -> TokenResponse:
    """Google sign-in via Supabase — an ADDITIONAL entry point into the
    existing session system, not a replacement for it. The Supabase token is
    verified via JWKS and then exchanged for this app's own access+refresh
    token pair (the same TokenResponse shape signup/login already return);
    nothing downstream of this endpoint needs to know Google was involved.
    """
    try:
        claims = verify_supabase_token(req.supabase_access_token)
    except SupabaseNotConfigured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google login is not configured")
    except TokenError:
        security_logger.warning("google login rejected: invalid supabase token",
                                extra={"event": "google_login_invalid_token"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired Google session")

    try:
        user, is_new = oauth_google.login_or_signup_with_google(session, claims)
    except oauth_google.UnverifiedEmail:
        security_logger.warning("google login rejected: unverified email",
                                extra={"event": "google_login_unverified_email"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google account email is not verified")

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account is disabled")

    security_logger.info("google login succeeded", extra={
        "event": "google_signup_succeeded" if is_new else "google_login_succeeded",
        "user_id": str(user.id), "email": user.email,
    })
    return _token_for(session, user)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_RATE_LIMIT)
def forgot_password(request: Request, response: Response, req: ForgotPasswordRequest,
                    background_tasks: BackgroundTasks,
                    session: Session = Depends(get_db), mailer=Depends(get_mailer)) -> None:
    """Always 204 regardless of whether the email exists. The email is sent
    AFTER the response (BackgroundTasks): a synchronous SMTP round-trip only
    on the account-exists path made response latency an enumeration signal."""
    raw_token = password_reset_service.create_reset_token(
        session, email=req.email, expire_minutes=get_settings().password_reset_expire_minutes,
    )
    if raw_token is not None:
        base = get_settings().frontend_base_url.rstrip("/")
        reset_url = f"{base}/reset-password/{raw_token}"
        background_tasks.add_task(_send_best_effort, mailer.send_password_reset,
                                  to_email=req.email, reset_url=reset_url)
    else:
        # Timing parity: schedule the same-shaped (no-op) background task so
        # both branches do identical pre-response work — create_reset_token
        # already equalizes the DB/token work internally.
        background_tasks.add_task(_send_best_effort, _noop_send)
    security_logger.info("forgot-password requested", extra={"event": "forgot_password_requested"})


def _noop_send(**_kwargs) -> None:
    """Parity placeholder for the no-account branch of forgot-password."""


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_RATE_LIMIT)
def reset_password(request: Request, response: Response, req: ResetPasswordRequest,
                   session: Session = Depends(get_db)) -> None:
    try:
        user = password_reset_service.reset_password(
            session, raw_token=req.token, new_password=req.new_password,
        )
    except password_reset_service.ResetTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired reset link")
    security_logger.info("password reset completed", extra={
        "event": "password_reset_completed", "user_id": str(user.id),
    })


def _me_response(session: Session, user: User) -> MeResponse:
    rows = session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.company_id)
        .where(Membership.user_id == user.id)
    ).all()
    orgs = [OrgOut(id=str(o.id), name=o.name, role=m.role.value) for m, o in rows]
    return MeResponse(user_id=str(user.id), email=user.email,
                      full_name=user.full_name, organizations=orgs)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> MeResponse:
    return _me_response(session, user)


@router.patch("/me", response_model=MeResponse)
def update_me(req: UpdateMeRequest, user: User = Depends(get_current_user),
              session: Session = Depends(get_db)) -> MeResponse:
    """Update the current user's own editable profile fields (full name).

    Self-scoped by get_current_user — a user can only ever edit their own
    row; no company/admin authorization is involved because this touches no
    org-scoped data. Returns the same MeResponse shape as GET /me so the
    frontend can refresh its cached user in one round trip.
    """
    # Normalize: treat an all-whitespace name as cleared, so the UI never
    # persists a blank-but-nonempty value.
    name = (req.full_name or "").strip()
    user.full_name = name or None
    session.commit()
    security_logger.info("profile updated", extra={
        "event": "profile_updated", "user_id": str(user.id),
    })
    return _me_response(session, user)


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
@limiter.limit(AUTH_RATE_LIMIT)
def logout(request: Request, response: Response, req: LogoutRequest,
          session: Session = Depends(get_db)) -> None:
    """Revoke one refresh token — ends this session/device only."""
    revoked = refresh_tokens.revoke(session, req.refresh_token)
    if revoked:
        security_logger.info("logout", extra={"event": "logout"})


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(AUTH_RATE_LIMIT)
def logout_all(request: Request, response: Response, user: User = Depends(get_current_user),
               session: Session = Depends(get_db)) -> None:
    """Revoke every refresh token for the current user — signs out all devices."""
    count = refresh_tokens.revoke_all(session, user.id)
    security_logger.info("logout-all", extra={
        "event": "logout_all", "user_id": str(user.id), "sessions_revoked": count,
    })


def _token_for(session: Session, user: User) -> TokenResponse:
    access = create_access_token(str(user.id), extra={"email": user.email})
    refresh = refresh_tokens.issue(session, user.id)
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), email=user.email)
