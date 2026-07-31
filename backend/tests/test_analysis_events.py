"""SSE analysis-events auth (.3): _resolve_user must never 500 on a bad token."""
from fastapi import HTTPException

from app.auth.tokens import create_access_token
from app.routers.analysis_events import _resolve_user
from tests.fakes import FakeSession


def test_resolve_user_missing_token_raises_401():
    try:
        _resolve_user(FakeSession(), None)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_resolve_user_invalid_token_raises_401():
    try:
        _resolve_user(FakeSession(), "not-a-real-token")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_resolve_user_non_uuid_sub_raises_401_not_500():
    """A validly-signed token whose sub isn't a UUID must answer 401, the
    same as deps.get_current_user — not an unhandled ValueError. This is
    the exact gap _resolve_user had until its own uuid.UUID(sub) parse was
    wrapped in the same try/except get_current_user already uses."""
    token = create_access_token("not-a-uuid")
    try:
        _resolve_user(FakeSession(), token)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
    except ValueError:
        assert False, "uuid.UUID(sub) must be caught, not left to propagate as a 500"
