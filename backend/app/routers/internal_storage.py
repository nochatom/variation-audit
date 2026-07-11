"""Storage health diagnostics — read-only, admin-only.

Verifies the object-storage backend build_loader() would resolve to (see
app/storage.py's resolution order: local dir -> Supabase -> S3) is actually
usable, without ever calling put()/delete() and without ever returning the
service_role key, a JWT, or any other credential — see
app.storage.check_storage_health's docstring for what `details` can contain.

Auth follows the same pattern as /internal/providers (Phase 5): this data is
platform-wide infrastructure state, not any one org's, so it requires the
caller be an admin of at least one organization (require_any_org_admin)
rather than the usual org-scoped require_admin.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.deps import require_any_org_admin
from app.models import User
from app.storage import check_storage_health

router = APIRouter(prefix="/internal/storage", tags=["internal-storage"])


@router.get("/health")
def get_storage_health(_admin: User = Depends(require_any_org_admin)) -> dict:
    return check_storage_health()
