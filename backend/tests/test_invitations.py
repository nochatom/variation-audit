"""Organization invitations (.19a): service logic + endpoints.

Covers the reported bug directly: "Invite member" must never require the
invited email to already have an account, and must never return "no user
with that email" (see test_create_invitation_endpoint_new_email_never_404s).
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.auth.security import hash_password
from app.main import app
from app.mailer import get_mailer
from app.models import (
    Invitation,
    Membership,
    MembershipRole,
    Organization,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.services import invitations as inv
from tests.fakes import FakeResult, FakeSession


def _now():
    return datetime.now(timezone.utc)


def _user(email="invitee@firm.com"):
    return User(id=uuid.uuid4(), email=email, password_hash="x", is_active=True)


def _free_sub(company_id):
    """A Free-plan subscription with room under its seat limit — used to
    satisfy the seat-limit check the invitation-create endpoint now runs
    before delegating to inv_service.create_invitation (see
    app/routers/invitations.py, app/services/billing.py:enforce_seat_limit)."""
    return Subscription(id=uuid.uuid4(), company_id=company_id, plan=PlanTier.free,
                        status=SubscriptionStatus.active)


def _fixture_invitation(*, company_id=None, email="invitee@firm.com",
                        accepted=False, revoked=False, expired=False,
                        role=MembershipRole.member):
    company_id = company_id or uuid.uuid4()
    secret = "test-invite-secret-abc123"
    row = Invitation(
        id=uuid.uuid4(), company_id=company_id, email=email, role=role,
        token_hash=inv._hash(secret),
        expires_at=_now() + (timedelta(days=-1) if expired else timedelta(days=7)),
        accepted_at=_now() if accepted else None,
        revoked_at=_now() if revoked else None,
    )
    raw = inv._encode(row.id, secret)
    return row, raw


class FakeMailer:
    def __init__(self):
        self.sent: list[dict] = []

    def send_invitation(self, **kwargs):
        self.sent.append(kwargs)


class FailingMailer:
    """Simulates an SMTP/network failure on send."""

    def send_invitation(self, **kwargs):
        raise ConnectionRefusedError("smtp connection refused")


# -- service: create_invitation ----------------------------------------------
def test_create_invitation_for_unknown_email_succeeds():
    """The core bug fix: no account needs to exist for this email."""
    session = FakeSession(results=[
        FakeResult(scalar=None),      # _user_by_email -> no such user
        FakeResult(scalars=[]),       # no stale pending invitation
    ])
    actor = _user("admin@firm.com")
    cid = uuid.uuid4()
    row, raw = inv.create_invitation(session, company_id=cid, actor=actor,
                                     email="brandnew@firm.com", role=MembershipRole.member)
    assert "." in raw
    assert row.email == "brandnew@firm.com"
    assert inv.status_of(row) == "pending"
    assert session.commits == 1
    assert len(session.added_of(Invitation)) == 1


def test_create_invitation_existing_user_not_yet_member_succeeds():
    existing = _user("existing@firm.com")
    session = FakeSession(results=[
        FakeResult(scalar=existing),  # _user_by_email -> found
        FakeResult(scalar=None),      # _membership -> not a member
        FakeResult(scalars=[]),       # no stale invitation
    ])
    actor = _user("admin@firm.com")
    row, raw = inv.create_invitation(session, company_id=uuid.uuid4(), actor=actor,
                                     email="existing@firm.com")
    assert row.email == "existing@firm.com"


def test_create_invitation_already_member_raises():
    existing = _user("member@firm.com")
    membership = Membership(id=uuid.uuid4(), user_id=existing.id, company_id=uuid.uuid4(),
                            role=MembershipRole.member)
    session = FakeSession(results=[
        FakeResult(scalar=existing),
        FakeResult(scalar=membership),
    ])
    actor = _user("admin@firm.com")
    try:
        inv.create_invitation(session, company_id=uuid.uuid4(), actor=actor, email="member@firm.com")
        assert False, "expected AlreadyMember"
    except inv.AlreadyMember:
        pass


def test_create_invitation_duplicate_pending_raises_instead_of_resending():
    """A still-pending (non-expired) invitation for the same (org, email)
    must block a second invite with a clear error, not silently resend."""
    still_pending, _ = _fixture_invitation(email="brandnew@firm.com")
    session = FakeSession(results=[
        FakeResult(scalar=None),               # _user_by_email -> no account
        FakeResult(scalars=[still_pending]),   # one open, non-expired row
    ])
    actor = _user("admin@firm.com")
    try:
        inv.create_invitation(session, company_id=uuid.uuid4(), actor=actor, email="brandnew@firm.com")
        assert False, "expected DuplicateInvitation"
    except inv.DuplicateInvitation:
        pass
    assert still_pending.revoked_at is None  # untouched — not silently revoked
    assert session.commits == 0  # nothing was created


def test_create_invitation_auto_revokes_expired_dangling_invite_and_succeeds():
    """An EXPIRED (but never accepted/revoked) invitation must not
    permanently block re-inviting the same email — it's garbage-collected
    on the next invite attempt instead of counting as a duplicate."""
    expired, _ = _fixture_invitation(email="brandnew@firm.com", expired=True)
    session = FakeSession(results=[
        FakeResult(scalar=None),
        FakeResult(scalars=[expired]),
    ])
    actor = _user("admin@firm.com")
    row, raw = inv.create_invitation(session, company_id=uuid.uuid4(), actor=actor, email="brandnew@firm.com")
    assert expired.revoked_at is not None  # auto-cleaned
    assert row.email == "brandnew@firm.com"
    assert "." in raw


# -- service: revoke_invitation -------------------------------------------------
def test_revoke_invitation_allows_pending():
    row, _ = _fixture_invitation()
    session = FakeSession(get_obj=row)
    actor = _user("admin@firm.com")
    inv.revoke_invitation(session, company_id=row.company_id, actor=actor, invitation_id=row.id)
    assert row.revoked_at is not None


def test_revoke_invitation_allows_expired():
    """An admin must be able to dismiss/revoke an expired-but-dangling
    invitation (it still shows in the pending list) — not just strictly
    "pending" ones."""
    row, _ = _fixture_invitation(expired=True)
    session = FakeSession(get_obj=row)
    actor = _user("admin@firm.com")
    inv.revoke_invitation(session, company_id=row.company_id, actor=actor, invitation_id=row.id)
    assert row.revoked_at is not None


def test_revoke_invitation_rejects_already_accepted():
    row, _ = _fixture_invitation(accepted=True)
    session = FakeSession(get_obj=row)
    actor = _user("admin@firm.com")
    try:
        inv.revoke_invitation(session, company_id=row.company_id, actor=actor, invitation_id=row.id)
        assert False, "expected InvitationError"
    except inv.InvitationError:
        pass


def test_revoke_invitation_rejects_already_revoked():
    row, _ = _fixture_invitation(revoked=True)
    session = FakeSession(get_obj=row)
    actor = _user("admin@firm.com")
    try:
        inv.revoke_invitation(session, company_id=row.company_id, actor=actor, invitation_id=row.id)
        assert False, "expected InvitationError"
    except inv.InvitationError:
        pass


def test_revoke_invitation_wrong_org_404s():
    row, _ = _fixture_invitation()
    session = FakeSession(get_obj=row)
    actor = _user("admin@firm.com")
    try:
        inv.revoke_invitation(session, company_id=uuid.uuid4(), actor=actor, invitation_id=row.id)
        assert False, "expected InvitationNotFound"
    except inv.InvitationNotFound:
        pass


# -- service: get_invitation_by_token ------------------------------------------
def test_get_invitation_by_token_malformed_raises():
    session = FakeSession()
    try:
        inv.get_invitation_by_token(session, "not-a-valid-token")
        assert False, "expected InvalidToken"
    except inv.InvalidToken:
        pass


def test_get_invitation_by_token_unknown_id_raises():
    session = FakeSession(get_obj=None)
    _, raw = _fixture_invitation()
    try:
        inv.get_invitation_by_token(session, raw)
        assert False, "expected InvalidToken"
    except inv.InvalidToken:
        pass


def test_get_invitation_by_token_wrong_secret_raises():
    row, _ = _fixture_invitation()
    session = FakeSession(get_obj=row)
    forged = inv._encode(row.id, "wrong-secret")
    try:
        inv.get_invitation_by_token(session, forged)
        assert False, "expected InvalidToken"
    except inv.InvalidToken:
        pass


def test_get_invitation_by_token_expired_raises():
    row, raw = _fixture_invitation(expired=True)
    session = FakeSession(get_obj=row)
    try:
        inv.get_invitation_by_token(session, raw)
        assert False, "expected InvitationExpired"
    except inv.InvitationExpired:
        pass


def test_get_invitation_by_token_revoked_raises():
    row, raw = _fixture_invitation(revoked=True)
    session = FakeSession(get_obj=row)
    try:
        inv.get_invitation_by_token(session, raw)
        assert False, "expected InvitationRevoked"
    except inv.InvitationRevoked:
        pass


def test_get_invitation_by_token_accepted_raises():
    row, raw = _fixture_invitation(accepted=True)
    session = FakeSession(get_obj=row)
    try:
        inv.get_invitation_by_token(session, raw)
        assert False, "expected InvitationAlreadyUsed"
    except inv.InvitationAlreadyUsed:
        pass


def test_get_invitation_by_token_valid_returns_row():
    row, raw = _fixture_invitation()
    session = FakeSession(get_obj=row)
    result = inv.get_invitation_by_token(session, raw)
    assert result is row


# -- service: accept_for_existing_user -----------------------------------------
def test_accept_for_existing_user_email_mismatch_raises():
    row, raw = _fixture_invitation(email="invitee@firm.com")
    session = FakeSession(get_obj=row)
    wrong_user = _user("someone-else@firm.com")
    try:
        inv.accept_for_existing_user(session, raw_token=raw, user=wrong_user)
        assert False, "expected EmailMismatch"
    except inv.EmailMismatch:
        pass


def test_accept_for_existing_user_creates_membership():
    row, raw = _fixture_invitation(email="invitee@firm.com", role=MembershipRole.admin)
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=None)])  # _membership -> not yet
    user = _user("invitee@firm.com")
    m = inv.accept_for_existing_user(session, raw_token=raw, user=user)
    assert m.company_id == row.company_id
    assert m.role == MembershipRole.admin
    assert row.accepted_at is not None
    assert row.accepted_by == user.id
    assert len(session.added_of(Membership)) == 1


def test_accept_for_existing_user_already_member_is_idempotent():
    row, raw = _fixture_invitation(email="invitee@firm.com")
    user = _user("invitee@firm.com")
    existing_membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=row.company_id,
                                     role=MembershipRole.member)
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=existing_membership)])
    m = inv.accept_for_existing_user(session, raw_token=raw, user=user)
    assert m is existing_membership
    assert len(session.added_of(Membership)) == 0  # no duplicate created
    assert row.accepted_at is not None


# -- service: register_and_accept ----------------------------------------------
def test_register_and_accept_creates_user_and_membership():
    row, raw = _fixture_invitation(email="newuser@firm.com", role=MembershipRole.member)
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=None)])  # _user_by_email -> none
    user, m = inv.register_and_accept(session, raw_token=raw, password="goodpassword1", full_name="New User")
    assert user.email == "newuser@firm.com"
    assert m.company_id == row.company_id
    assert row.accepted_at is not None
    assert len(session.added_of(User)) == 1
    assert len(session.added_of(Membership)) == 1


def test_register_and_accept_existing_email_raises():
    row, raw = _fixture_invitation(email="existing@firm.com")
    existing = _user("existing@firm.com")
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=existing)])
    try:
        inv.register_and_accept(session, raw_token=raw, password="goodpassword1", full_name=None)
        assert False, "expected EmailAlreadyRegistered"
    except inv.EmailAlreadyRegistered:
        pass


# -- endpoints ------------------------------------------------------------------
def _client(session, user=None, mailer=None):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    if mailer is not None:
        app.dependency_overrides[get_mailer] = lambda: mailer
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_create_invitation_endpoint_requires_admin():
    cid = uuid.uuid4()
    member_role = Membership(id=uuid.uuid4(), user_id=uuid.uuid4(), company_id=cid, role=MembershipRole.member)
    session = FakeSession(results=[FakeResult(scalar=member_role)])
    resp = _client(session, _user()).post(f"/orgs/{cid}/invitations", json={"email": "x@firm.com"})
    assert resp.status_code == 403


def test_create_invitation_endpoint_new_email_never_404s():
    """Direct regression test for the reported bug: inviting an email with no
    existing account must succeed (201), and must never surface the old
    "no user with that email" message anywhere in the response."""
    cid = uuid.uuid4()
    admin = _user("admin@firm.com")
    admin_membership = Membership(id=uuid.uuid4(), user_id=admin.id, company_id=cid, role=MembershipRole.admin)
    org = Organization(id=cid, name="Acme Constructions")
    session = FakeSession(
        results=[
            FakeResult(scalar=admin_membership),        # require_admin
            FakeResult(scalar=_free_sub(cid)),           # enforce_seat_limit: get_or_create_subscription
            FakeResult(scalars=[admin_membership]),      # enforce_seat_limit: seat count
            FakeResult(scalar=None),               # _user_by_email -> no account
            FakeResult(scalars=[]),                # no stale invite
            FakeResult(scalar=org),                # _org_name lookup
        ],
    )
    mailer = FakeMailer()
    resp = _client(session, admin, mailer).post(
        f"/orgs/{cid}/invitations", json={"email": "brandnew@nosuchaccount.com", "role": "member"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "no user with that email" not in resp.text.lower()
    assert body["email"] == "brandnew@nosuchaccount.com"
    assert body["status"] == "pending"
    assert body["accept_url"] and "/accept-invite/" in body["accept_url"]
    assert body["email_sent"] is True
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["to_email"] == "brandnew@nosuchaccount.com"


def test_create_invitation_endpoint_already_member_returns_409():
    cid = uuid.uuid4()
    admin = _user("admin@firm.com")
    admin_membership = Membership(id=uuid.uuid4(), user_id=admin.id, company_id=cid, role=MembershipRole.admin)
    existing = _user("existing@firm.com")
    existing_membership = Membership(id=uuid.uuid4(), user_id=existing.id, company_id=cid, role=MembershipRole.member)
    session = FakeSession(results=[
        FakeResult(scalar=admin_membership),
        FakeResult(scalar=_free_sub(cid)),           # enforce_seat_limit: get_or_create_subscription
        FakeResult(scalars=[admin_membership]),      # enforce_seat_limit: seat count
        FakeResult(scalar=existing),
        FakeResult(scalar=existing_membership),
    ])
    resp = _client(session, admin, FakeMailer()).post(
        f"/orgs/{cid}/invitations", json={"email": "existing@firm.com"},
    )
    assert resp.status_code == 409


def test_create_invitation_endpoint_duplicate_returns_409_with_clear_message():
    """Direct regression test for the audit finding: re-inviting an email
    that already has a pending invitation must be rejected with a clear
    validation error, not silently create a second active invitation."""
    cid = uuid.uuid4()
    admin = _user("admin@firm.com")
    admin_membership = Membership(id=uuid.uuid4(), user_id=admin.id, company_id=cid, role=MembershipRole.admin)
    still_pending, _ = _fixture_invitation(company_id=cid, email="dup@firm.com")
    session = FakeSession(results=[
        FakeResult(scalar=admin_membership),
        FakeResult(scalar=_free_sub(cid)),           # enforce_seat_limit: get_or_create_subscription
        FakeResult(scalars=[admin_membership]),      # enforce_seat_limit: seat count
        FakeResult(scalar=None),                    # _user_by_email -> no account
        FakeResult(scalars=[still_pending]),         # already an active invite
    ])
    resp = _client(session, admin, FakeMailer()).post(
        f"/orgs/{cid}/invitations", json={"email": "dup@firm.com"},
    )
    assert resp.status_code == 409
    assert "active invitation already exists" in resp.json()["error"]["message"].lower()


def test_create_invitation_endpoint_email_failure_surfaces_email_sent_false():
    """Direct regression test for the audit finding: a mail delivery failure
    must not be silently swallowed — it must be visible in the response
    (email_sent=False) while the invitation itself still succeeds, since the
    accept_url copy-link fallback still works without email."""
    cid = uuid.uuid4()
    admin = _user("admin@firm.com")
    admin_membership = Membership(id=uuid.uuid4(), user_id=admin.id, company_id=cid, role=MembershipRole.admin)
    org = Organization(id=cid, name="Acme Constructions")
    session = FakeSession(results=[
        FakeResult(scalar=admin_membership),
        FakeResult(scalar=_free_sub(cid)),           # enforce_seat_limit: get_or_create_subscription
        FakeResult(scalars=[admin_membership]),      # enforce_seat_limit: seat count
        FakeResult(scalar=None),
        FakeResult(scalars=[]),
        FakeResult(scalar=org),
    ])
    resp = _client(session, admin, FailingMailer()).post(
        f"/orgs/{cid}/invitations", json={"email": "brandnew@nosuchaccount.com"},
    )
    assert resp.status_code == 201  # invitation creation itself must not fail
    body = resp.json()
    assert body["email_sent"] is False
    assert body["accept_url"]  # copy-link fallback still present


def test_list_invitations_endpoint():
    cid = uuid.uuid4()
    admin = _user("admin@firm.com")
    admin_membership = Membership(id=uuid.uuid4(), user_id=admin.id, company_id=cid, role=MembershipRole.admin)
    pending, _ = _fixture_invitation(company_id=cid, email="a@firm.com")
    session = FakeSession(results=[
        FakeResult(scalar=admin_membership),
        FakeResult(scalars=[pending]),
    ])
    resp = _client(session, admin).get(f"/orgs/{cid}/invitations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1 and body[0]["email"] == "a@firm.com"


def test_revoke_invitation_endpoint():
    cid = uuid.uuid4()
    admin = _user("admin@firm.com")
    admin_membership = Membership(id=uuid.uuid4(), user_id=admin.id, company_id=cid, role=MembershipRole.admin)
    row, _ = _fixture_invitation(company_id=cid)
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=admin_membership)])
    resp = _client(session, admin).delete(f"/orgs/{cid}/invitations/{row.id}")
    assert resp.status_code == 204
    assert row.revoked_at is not None


def test_preview_invitation_endpoint_public_no_auth():
    row, raw = _fixture_invitation(email="invitee@firm.com")
    org = Organization(id=row.company_id, name="Acme Constructions")
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=org), FakeResult(scalar=None)])
    app.dependency_overrides[get_db] = lambda: session
    resp = TestClient(app).get(f"/invitations/{raw}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "invitee@firm.com"
    assert body["org_name"] == "Acme Constructions"
    assert body["account_exists"] is False


def test_preview_invitation_endpoint_invalid_token_404s():
    session = FakeSession(get_obj=None)
    app.dependency_overrides[get_db] = lambda: session
    resp = TestClient(app).get("/invitations/bogus.token")
    assert resp.status_code == 404


def test_preview_invitation_endpoint_expired_returns_410():
    row, raw = _fixture_invitation(expired=True)
    session = FakeSession(get_obj=row)
    app.dependency_overrides[get_db] = lambda: session
    resp = TestClient(app).get(f"/invitations/{raw}")
    assert resp.status_code == 410


def test_accept_invitation_endpoint_wrong_email_403s():
    row, raw = _fixture_invitation(email="invitee@firm.com")
    session = FakeSession(get_obj=row)
    wrong_user = _user("someone-else@firm.com")
    resp = _client(session, wrong_user).post(f"/invitations/{raw}/accept")
    assert resp.status_code == 403


def test_accept_invitation_endpoint_success():
    row, raw = _fixture_invitation(email="invitee@firm.com")
    user = _user("invitee@firm.com")
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=None)])
    resp = _client(session, user).post(f"/invitations/{raw}/accept")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_id"] == str(row.company_id)


def test_register_via_invitation_endpoint_success():
    row, raw = _fixture_invitation(email="newuser@firm.com")
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=None)])
    resp = _client(session).post(
        f"/invitations/{raw}/register", json={"password": "goodpassword1", "full_name": "New User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["email"] == "newuser@firm.com"


def test_register_via_invitation_endpoint_existing_email_409s():
    row, raw = _fixture_invitation(email="existing@firm.com")
    existing = _user("existing@firm.com")
    session = FakeSession(get_obj=row, results=[FakeResult(scalar=existing)])
    resp = _client(session).post(
        f"/invitations/{raw}/register", json={"password": "goodpassword1"},
    )
    assert resp.status_code == 409


def test_accept_invitation_endpoint_rate_limiting():
    from app.rate_limit import limiter

    limiter.reset()
    try:
        row, raw = _fixture_invitation(email="invitee@firm.com")
        user = _user("invitee@firm.com")
        session = FakeSession(get_obj=row, results=[FakeResult(scalar=None) for _ in range(6)])
        client = _client(session, user)
        responses = [client.post(f"/invitations/{raw}/accept") for _ in range(6)]
        statuses = [r.status_code for r in responses]
        assert statuses[0] == 200
        assert statuses[1:5] == [410] * 4
        assert statuses[5] == 429
        assert "retry-after" in responses[5].headers
    finally:
        limiter.reset()
