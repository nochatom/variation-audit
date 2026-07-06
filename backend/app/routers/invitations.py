"""Organization invitation endpoints (.19a).

Two resource groups:
  * /orgs/{company_id}/invitations — admin-only management (create/list/revoke)
  * /invitations/{token}           — public, token-addressed accept flow

"Invite member" never requires the invited email to already have an account:
POST .../invitations always creates a pending Invitation, notifying the
invitee by email (best-effort — a mail failure doesn't fail the request) and
returning an accept_url the admin UI can also show as a "copy invite link"
fallback (Slack/Linear/Notion pattern), since local/dev environments without
SMTP configured have no other way to retrieve it.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db, require_admin
from app.auth.refresh_tokens import issue as issue_refresh_token
from app.auth.router import TokenResponse
from app.auth.tokens import create_access_token
from app.config import get_settings
from app.logging_config import security_logger
from app.mailer import get_mailer
from app.models import Invitation, MembershipRole, User
from app.rate_limit import AUTH_LIMIT as AUTH_RATE_LIMIT
from app.rate_limit import INVITATION_LIMIT
from app.rate_limit import limiter
from app.services import billing as billing_service
from app.services import invitations as inv_service

org_router = APIRouter(prefix="/orgs/{company_id}/invitations", tags=["invitations"])
public_router = APIRouter(prefix="/invitations", tags=["invitations"])


# ---- schemas ---------------------------------------------------------------
class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.member


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    status: str
    invited_by: str | None = None
    created_at: str
    expires_at: str
    accept_url: str | None = None
    # None on list/revoke responses (no send attempted there); True/False on
    # the create response depending on whether the notification email
    # actually went out — never silently omitted just because it failed.
    email_sent: bool | None = None


class InvitationPreview(BaseModel):
    email: str
    org_name: str
    role: str
    account_exists: bool


class RegisterViaInvitationRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)


class AcceptOut(BaseModel):
    company_id: str
    role: str


def _accept_url(raw_token: str) -> str:
    base = get_settings().frontend_base_url.rstrip("/")
    return f"{base}/accept-invite/{raw_token}"


def _out(inv: Invitation, *, raw_token: str | None = None,
        email_sent: bool | None = None) -> InvitationOut:
    return InvitationOut(
        id=str(inv.id), email=inv.email, role=inv.role.value,
        status=inv_service.status_of(inv),
        invited_by=str(inv.invited_by) if inv.invited_by else None,
        created_at=inv.created_at.isoformat() if inv.created_at else "",
        expires_at=inv.expires_at.isoformat() if inv.expires_at else "",
        accept_url=_accept_url(raw_token) if raw_token else None,
        email_sent=email_sent,
    )


# ---- admin management -------------------------------------------------------
@org_router.get("", response_model=list[InvitationOut])
def list_invitations(company_id: uuid.UUID, user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> list[InvitationOut]:
    require_admin(session, user, company_id)
    return [_out(i) for i in inv_service.list_pending(session, company_id)]


@org_router.post("", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(INVITATION_LIMIT)
def create_invitation(request: Request, response: Response, company_id: uuid.UUID,
                      req: CreateInvitationRequest,
                      user: User = Depends(get_current_user),
                      session: Session = Depends(get_db),
                      mailer=Depends(get_mailer)) -> InvitationOut:
    require_admin(session, user, company_id)
    try:
        billing_service.enforce_seat_limit(session, company_id)
    except billing_service.PlanLimitExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"error_code": exc.code, "message": str(exc)})
    try:
        inv, raw_token = inv_service.create_invitation(
            session, company_id=company_id, actor=user, email=req.email, role=req.role,
            expire_days=get_settings().invitation_expire_days,
        )
    except inv_service.AlreadyMember:
        raise HTTPException(status.HTTP_409_CONFLICT, "already a member")
    except inv_service.DuplicateInvitation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "an active invitation already exists for this email — revoke it first to re-invite",
        )

    accept_url = _accept_url(raw_token)
    email_sent = True
    try:
        mailer.send_invitation(
            to_email=inv.email, org_name=_org_name(session, company_id),
            inviter_name=user.full_name or user.email, accept_url=accept_url,
        )
    except Exception:  # noqa: BLE001 — a mail failure must not fail invitation
        # creation (the accept_url "copy link" fallback still works), but it
        # must never be silent: logged here for ops, and surfaced to the
        # caller via email_sent=False so the admin UI can tell the invited
        # person to use the copy-link fallback instead of waiting on an
        # email that never arrived.
        email_sent = False
        security_logger.warning("invitation email send failed", extra={
            "event": "invitation_email_failed", "invitation_id": str(inv.id),
        }, exc_info=True)
    security_logger.info("invitation created", extra={
        "event": "invitation_created", "invitation_id": str(inv.id),
        "company_id": str(company_id), "role": req.role.value, "email_sent": email_sent,
    })
    return _out(inv, raw_token=raw_token, email_sent=email_sent)


@org_router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(company_id: uuid.UUID, invitation_id: uuid.UUID,
                      user: User = Depends(get_current_user),
                      session: Session = Depends(get_db)) -> None:
    require_admin(session, user, company_id)
    try:
        inv_service.revoke_invitation(session, company_id=company_id, actor=user,
                                      invitation_id=invitation_id)
    except inv_service.InvitationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found")
    except inv_service.InvitationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


def _org_name(session: Session, company_id: uuid.UUID) -> str:
    org = inv_service.get_organization(session, company_id)
    return org.name if org else ""


# ---- public accept flow ------------------------------------------------------
def _map_invitation_error(exc: inv_service.InvitationError) -> HTTPException:
    if isinstance(exc, inv_service.InvitationExpired):
        return HTTPException(status.HTTP_410_GONE, "invitation has expired")
    if isinstance(exc, (inv_service.InvitationAlreadyUsed, inv_service.InvitationRevoked)):
        return HTTPException(status.HTTP_410_GONE, "invitation is no longer valid")
    if isinstance(exc, inv_service.EmailMismatch):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return HTTPException(status.HTTP_404_NOT_FOUND, "invalid invitation link")


@public_router.get("/{token}", response_model=InvitationPreview)
@limiter.limit(AUTH_RATE_LIMIT)
def preview_invitation(request: Request, response: Response, token: str,
                       session: Session = Depends(get_db)) -> InvitationPreview:
    try:
        p = inv_service.preview(session, token)
    except inv_service.InvitationError as exc:
        raise _map_invitation_error(exc)
    return InvitationPreview(**p)


@public_router.post("/{token}/accept", response_model=AcceptOut)
def accept_invitation(token: str, user: User = Depends(get_current_user),
                      session: Session = Depends(get_db)) -> AcceptOut:
    """Accept as an already-authenticated user (must be logged in as the
    invited email — see app/services/invitations.py:accept_for_existing_user)."""
    try:
        m = inv_service.accept_for_existing_user(session, raw_token=token, user=user)
    except inv_service.InvitationError as exc:
        raise _map_invitation_error(exc)
    security_logger.info("invitation accepted", extra={
        "event": "invitation_accepted", "user_id": str(user.id), "company_id": str(m.company_id),
    })
    return AcceptOut(company_id=str(m.company_id), role=m.role.value)


@public_router.post("/{token}/register", response_model=TokenResponse,
                    status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
def register_via_invitation(request: Request, response: Response, token: str,
                            req: RegisterViaInvitationRequest,
                            session: Session = Depends(get_db)) -> TokenResponse:
    """Create a brand-new account for the invited email and accept in one
    step — no org_name needed, the org comes from the invitation."""
    try:
        user, m = inv_service.register_and_accept(
            session, raw_token=token, password=req.password, full_name=req.full_name,
        )
    except inv_service.EmailAlreadyRegistered:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "an account already exists for this email — log in to accept the invitation",
        )
    except inv_service.InvitationError as exc:
        raise _map_invitation_error(exc)

    security_logger.info("invitation accepted via registration", extra={
        "event": "invitation_registered", "user_id": str(user.id), "company_id": str(m.company_id),
    })
    access = create_access_token(str(user.id), extra={"email": user.email})
    refresh = issue_refresh_token(session, user.id)
    return TokenResponse(access_token=access, refresh_token=refresh,
                         user_id=str(user.id), email=user.email)
