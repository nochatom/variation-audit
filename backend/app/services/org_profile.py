"""Organisation profile + offices (0017) — admin-writable, audited.

Separate module from services/orgs.py, which owns membership. This one owns
the org's own identity (legal name, ABN, contact details, logo) and its
offices. Both are audited through the same audit_log the membership service
writes to, so "who changed the ABN" is answerable.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Office, Organization, User

AU_STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}

# Editable identity fields. `name` is included; `id`/timestamps/logo_key are
# not — logo_key is written only by the upload route, never by a JSON patch.
PROFILE_FIELDS = ("name", "legal_name", "abn", "acn", "website", "phone", "primary_state")
OFFICE_FIELDS = ("label", "address", "suburb", "state", "postcode", "phone", "is_primary")


class OrgNotFound(Exception):
    pass


class OfficeNotFound(Exception):
    pass


class InvalidProfile(Exception):
    """Validation failure with a human-readable, field-specific message."""


def _digits(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def validate_abn(abn: str) -> str:
    """Normalise to 11 digits and verify the ATO modulus-89 checksum.

    The database CHECK only enforces shape. A typo'd ABN that happens to be
    11 digits would pass the constraint and then fail on a real claim, so the
    checksum is verified here — this is the published ATO algorithm: subtract
    1 from the first digit, apply the fixed weights, and the weighted sum must
    be divisible by 89.
    """
    digits = _digits(abn)
    if len(digits) != 11:
        raise InvalidProfile("ABN must be 11 digits.")
    weights = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
    total = sum((int(d) - (1 if i == 0 else 0)) * w for i, (d, w) in enumerate(zip(digits, weights)))
    if total % 89 != 0:
        raise InvalidProfile("That ABN doesn't pass the ATO checksum — check for a typo.")
    return digits


def validate_acn(acn: str) -> str:
    digits = _digits(acn)
    if len(digits) != 9:
        raise InvalidProfile("ACN must be 9 digits.")
    return digits


def get_org(session: Session, company_id: uuid.UUID) -> Organization:
    org = session.get(Organization, company_id)
    if org is None:
        raise OrgNotFound(str(company_id))
    return org


def update_org(session: Session, *, company_id: uuid.UUID, actor: User,
               changes: dict) -> Organization:
    org = get_org(session, company_id)
    before, after = {}, {}

    for field in PROFILE_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if isinstance(value, str):
            value = value.strip() or None

        if value is not None:
            if field == "abn":
                value = validate_abn(value)
            elif field == "acn":
                value = validate_acn(value)
            elif field == "primary_state" and value.upper() not in AU_STATES:
                raise InvalidProfile(f"{value} isn't an Australian state or territory.")
            elif field == "primary_state":
                value = value.upper()
            elif field == "name" and not value:
                raise InvalidProfile("Organisation name can't be empty.")

        if field == "name" and value is None:
            raise InvalidProfile("Organisation name can't be empty.")

        current = getattr(org, field)
        if current != value:
            before[field] = current
            after[field] = value
            setattr(org, field, value)

    if after:
        session.add(AuditLog(
            company_id=company_id, actor_user_id=actor.id, entity_type="organization",
            entity_id=company_id, action="organization.updated", before=before, after=after,
        ))
    return org


def set_logo_key(session: Session, *, company_id: uuid.UUID, actor: User,
                 logo_key: str | None) -> Organization:
    org = get_org(session, company_id)
    before = {"logo_key": org.logo_key}
    org.logo_key = logo_key
    session.add(AuditLog(
        company_id=company_id, actor_user_id=actor.id, entity_type="organization",
        entity_id=company_id, action="organization.logo_updated",
        before=before, after={"logo_key": logo_key},
    ))
    return org


# ---- offices -------------------------------------------------------------
def list_offices(session: Session, company_id: uuid.UUID) -> list[Office]:
    return list(session.execute(
        select(Office)
        .where(Office.company_id == company_id)
        # Primary first, then alphabetical — a stable order the UI can rely on.
        .order_by(Office.is_primary.desc(), Office.label)
    ).scalars())


def _clear_other_primaries(session: Session, company_id: uuid.UUID, keep_id: uuid.UUID | None) -> None:
    """Demote any other primary office.

    The partial unique index makes two primaries impossible at the database
    level, so without this a second "make primary" would raise IntegrityError
    instead of doing the obvious thing.
    """
    for other in session.execute(
        select(Office).where(Office.company_id == company_id, Office.is_primary.is_(True))
    ).scalars():
        if keep_id is None or other.id != keep_id:
            other.is_primary = False
    session.flush()


def _validate_office(values: dict) -> dict:
    clean = {}
    for field in OFFICE_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if isinstance(value, str):
            value = value.strip() or None
        if field == "state" and value:
            if value.upper() not in AU_STATES:
                raise InvalidProfile(f"{value} isn't an Australian state or territory.")
            value = value.upper()
        if field == "postcode" and value:
            if not re.fullmatch(r"[0-9]{4}", value):
                raise InvalidProfile("Postcode must be 4 digits.")
        clean[field] = value
    if "label" in clean and not clean["label"]:
        raise InvalidProfile("Office name can't be empty.")
    return clean


def create_office(session: Session, *, company_id: uuid.UUID, actor: User, values: dict) -> Office:
    clean = _validate_office(values)
    if not clean.get("label"):
        raise InvalidProfile("Office name is required.")

    existing = list_offices(session, company_id)
    # First office is primary by definition — an org with offices but no
    # primary one is a state nothing downstream knows how to interpret.
    if not existing:
        clean["is_primary"] = True
    if clean.get("is_primary"):
        _clear_other_primaries(session, company_id, keep_id=None)

    office = Office(company_id=company_id, **clean)
    session.add(office)
    session.flush()
    session.add(AuditLog(
        company_id=company_id, actor_user_id=actor.id, entity_type="office",
        entity_id=office.id, action="office.created", after=clean,
    ))
    return office


def update_office(session: Session, *, company_id: uuid.UUID, actor: User,
                  office_id: uuid.UUID, values: dict) -> Office:
    office = session.get(Office, office_id)
    if office is None or office.company_id != company_id:
        raise OfficeNotFound(str(office_id))

    clean = _validate_office(values)
    if clean.get("is_primary"):
        _clear_other_primaries(session, company_id, keep_id=office.id)
    elif clean.get("is_primary") is False and office.is_primary:
        raise InvalidProfile(
            "Set another office as primary instead of unsetting this one."
        )

    before, after = {}, {}
    for field, value in clean.items():
        current = getattr(office, field)
        if current != value:
            before[field] = current
            after[field] = value
            setattr(office, field, value)

    if after:
        session.add(AuditLog(
            company_id=company_id, actor_user_id=actor.id, entity_type="office",
            entity_id=office.id, action="office.updated", before=before, after=after,
        ))
    return office


def delete_office(session: Session, *, company_id: uuid.UUID, actor: User,
                  office_id: uuid.UUID) -> None:
    office = session.get(Office, office_id)
    if office is None or office.company_id != company_id:
        raise OfficeNotFound(str(office_id))

    remaining = [o for o in list_offices(session, company_id) if o.id != office_id]
    was_primary = office.is_primary

    session.add(AuditLog(
        company_id=company_id, actor_user_id=actor.id, entity_type="office",
        entity_id=office.id, action="office.deleted",
        before={"label": office.label, "is_primary": office.is_primary}, after=None,
    ))
    session.delete(office)
    session.flush()

    # Deleting the primary must not leave the org without one.
    if was_primary and remaining:
        remaining[0].is_primary = True
