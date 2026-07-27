"""Organisation profile + offices endpoints (0017).

Reads are open to any member — the org's own name, ABN and offices are things
every user of the app legitimately needs to see. Writes are admin-only, the
same boundary member management uses.

Kept in its own router because routers/orgs.py is mounted at
/orgs/{company_id}/members and owns membership exclusively.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import ensure_member, get_current_user, get_db, require_admin
from app.models import Office, Organization, User
from app.services import org_profile as profile_service

router = APIRouter(prefix="/orgs/{company_id}", tags=["organizations"])


class OrganizationOut(BaseModel):
    id: str
    name: str
    legal_name: str | None = None
    abn: str | None = None
    acn: str | None = None
    website: str | None = None
    phone: str | None = None
    logo_key: str | None = None
    primary_state: str | None = None


class OrganizationUpdate(BaseModel):
    """Every field optional — this is a partial update. Explicit null clears a
    value; an omitted key leaves it untouched, which model_dump(exclude_unset)
    is what distinguishes."""

    name: str | None = Field(default=None, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    abn: str | None = Field(default=None, max_length=20)
    acn: str | None = Field(default=None, max_length=20)
    website: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=50)
    primary_state: str | None = Field(default=None, max_length=3)


class OfficeOut(BaseModel):
    id: str
    label: str
    address: str | None = None
    suburb: str | None = None
    state: str | None = None
    postcode: str | None = None
    phone: str | None = None
    is_primary: bool


class OfficeCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    suburb: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=3)
    postcode: str | None = Field(default=None, max_length=4)
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool = False


class OfficeUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    suburb: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=3)
    postcode: str | None = Field(default=None, max_length=4)
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool | None = None


def _org_out(org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=str(org.id), name=org.name, legal_name=org.legal_name, abn=org.abn,
        acn=org.acn, website=org.website, phone=org.phone, logo_key=org.logo_key,
        primary_state=org.primary_state,
    )


def _office_out(o: Office) -> OfficeOut:
    return OfficeOut(
        id=str(o.id), label=o.label, address=o.address, suburb=o.suburb,
        state=o.state, postcode=o.postcode, phone=o.phone, is_primary=o.is_primary,
    )


@router.get("", response_model=OrganizationOut)
def get_organization(company_id: uuid.UUID, user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> OrganizationOut:
    ensure_member(session, user, company_id)
    try:
        return _org_out(profile_service.get_org(session, company_id))
    except profile_service.OrgNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")


@router.patch("", response_model=OrganizationOut)
def update_organization(company_id: uuid.UUID, req: OrganizationUpdate,
                        user: User = Depends(get_current_user),
                        session: Session = Depends(get_db)) -> OrganizationOut:
    require_admin(session, user, company_id)
    try:
        org = profile_service.update_org(
            session, company_id=company_id, actor=user,
            changes=req.model_dump(exclude_unset=True),
        )
    except profile_service.OrgNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
    except profile_service.InvalidProfile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    session.commit()
    return _org_out(org)


@router.get("/offices", response_model=list[OfficeOut])
def list_offices(company_id: uuid.UUID, user: User = Depends(get_current_user),
                 session: Session = Depends(get_db)) -> list[OfficeOut]:
    ensure_member(session, user, company_id)
    return [_office_out(o) for o in profile_service.list_offices(session, company_id)]


@router.post("/offices", response_model=OfficeOut, status_code=status.HTTP_201_CREATED)
def create_office(company_id: uuid.UUID, req: OfficeCreate,
                  user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> OfficeOut:
    require_admin(session, user, company_id)
    try:
        office = profile_service.create_office(
            session, company_id=company_id, actor=user, values=req.model_dump(),
        )
    except profile_service.InvalidProfile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    session.commit()
    return _office_out(office)


@router.patch("/offices/{office_id}", response_model=OfficeOut)
def update_office(company_id: uuid.UUID, office_id: uuid.UUID, req: OfficeUpdate,
                  user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> OfficeOut:
    require_admin(session, user, company_id)
    try:
        office = profile_service.update_office(
            session, company_id=company_id, actor=user, office_id=office_id,
            values=req.model_dump(exclude_unset=True),
        )
    except profile_service.OfficeNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "office not found")
    except profile_service.InvalidProfile as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    session.commit()
    return _office_out(office)


@router.delete("/offices/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_office(company_id: uuid.UUID, office_id: uuid.UUID,
                  user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> None:
    require_admin(session, user, company_id)
    try:
        profile_service.delete_office(
            session, company_id=company_id, actor=user, office_id=office_id,
        )
    except profile_service.OfficeNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "office not found")
    session.commit()
