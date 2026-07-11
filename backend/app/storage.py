"""Document content loaders (DocumentLoader implementations).

The worker needs raw document text given a storage_key. Production uses S3
(ap-southeast-2) or Supabase Storage; dev/tests can read from a local
directory.
"""
from __future__ import annotations

import os


class SupabaseStorageLoader:
    """Loads/stores document content in a private Supabase Storage bucket
    via direct REST calls to Supabase's Storage API — no supabase-py SDK
    dependency, matching this codebase's existing lightweight pattern for
    Supabase integration (see app/auth/supabase_jwt.py's raw JWKS fetch).

    Requires the service_role key (not the anon key): the bucket is
    private, and this loader only ever runs in a trusted server context
    (worker, API backend) — never exposed to a browser.
    """

    def __init__(self, project_url: str, service_role_key: str, bucket: str, client=None):
        import httpx  # already a dependency (app/engine/client.py)

        self.bucket = bucket
        self._base_url = f"{project_url.rstrip('/')}/storage/v1"
        # `client` is injectable so tests can pass an httpx.Client wired to
        # an httpx.MockTransport instead of hitting the real network —
        # production code always uses the default (a real client).
        self._client = client if client is not None else httpx.Client(
            headers={
                "Authorization": f"Bearer {service_role_key}",
                "apikey": service_role_key,
            },
            timeout=30.0,
        )

    def load(self, storage_key: str) -> str:
        resp = self._client.get(f"{self._base_url}/object/{self.bucket}/{storage_key}")
        resp.raise_for_status()
        return resp.content.decode("utf-8", errors="replace")

    def put(self, storage_key: str, data: bytes | str) -> str:
        body = data.encode("utf-8") if isinstance(data, str) else data
        resp = self._client.post(
            f"{self._base_url}/object/{self.bucket}/{storage_key}",
            content=body,
            headers={"Content-Type": "application/octet-stream", "x-upsert": "true"},
        )
        resp.raise_for_status()
        return storage_key

    def delete(self, storage_key: str) -> None:
        resp = self._client.delete(f"{self._base_url}/object/{self.bucket}/{storage_key}")
        if resp.status_code not in (200, 404):
            # A missing key is idempotent-success, same contract as S3/local
            # below; anything else (auth failure, network error) is real.
            resp.raise_for_status()


class S3DocumentLoader:
    """Loads document content from S3 (Sydney region for AU residency)."""

    def __init__(self, bucket: str, region: str = "ap-southeast-2",
                 endpoint_url: str | None = None):
        import boto3  # imported lazily so non-worker code needn't depend on it

        self.bucket = bucket
        self._s3 = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)

    def load(self, storage_key: str) -> str:
        obj = self._s3.get_object(Bucket=self.bucket, Key=storage_key)
        return obj["Body"].read().decode("utf-8", errors="replace")

    def put(self, storage_key: str, data: bytes | str) -> str:
        body = data.encode("utf-8") if isinstance(data, str) else data
        self._s3.put_object(Bucket=self.bucket, Key=storage_key, Body=body)
        return storage_key

    def delete(self, storage_key: str) -> None:
        # S3 delete_object is idempotent — a missing key is not an error.
        self._s3.delete_object(Bucket=self.bucket, Key=storage_key)


class LocalDocumentLoader:
    """Reads document content from a local directory. For dev/tests only."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def _safe_path(self, storage_key: str) -> str:
        """Every real storage_key is server-generated (see
        app.services.projects.add_document — always
        f"{company_id}/{project_id}/docs/{uuid}.txt", never derived from a
        caller-supplied filename), so this never rejects legitimate traffic
        today. It's a defense-in-depth guard against a future code path
        passing an untrusted key straight through: os.path.join silently
        discards base_dir entirely if storage_key were absolute, and `..`
        segments can otherwise escape it.
        """
        base = os.path.abspath(self.base_dir)
        path = os.path.abspath(os.path.join(base, storage_key))
        if os.path.commonpath([base, path]) != base:
            raise ValueError(f"storage_key resolves outside the document store: {storage_key!r}")
        return path

    def load(self, storage_key: str) -> str:
        path = self._safe_path(storage_key)
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def put(self, storage_key: str, data: bytes | str) -> str:
        path = self._safe_path(storage_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = data if isinstance(data, bytes) else data.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(body)
        return storage_key

    def delete(self, storage_key: str) -> None:
        path = self._safe_path(storage_key)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass  # already gone — same idempotent contract as S3


def build_loader():
    """Pick a loader from settings: local dir (dev/tests) if configured,
    else Supabase Storage if configured, else S3 (the original default)."""
    from app.config import get_settings

    s = get_settings()
    if s.local_doc_dir:
        return LocalDocumentLoader(s.local_doc_dir)
    if s.supabase_url and s.supabase_service_role_key:
        return SupabaseStorageLoader(s.supabase_url, s.supabase_service_role_key, s.supabase_storage_bucket)
    return S3DocumentLoader(s.s3_bucket, s.s3_region, s.s3_endpoint_url)


def get_store():
    """FastAPI dependency yielding the document store (overridable in tests)."""
    return build_loader()


class StorageConfigurationError(RuntimeError):
    """Raised at startup when production has no viable object-storage
    backend configured — see validate_production_storage_config."""


def validate_production_storage_config(settings) -> None:
    """Fail loudly at startup if production has no way to store documents.

    Mirrors this codebase's existing "fail at construction, not at first
    use" pattern (VA_JWT_SECRET, VA_AGENT_ROUTING_POLICY in app/config.py).
    A no-op outside production, and a no-op in production if VA_LOCAL_DOC_DIR
    is set — this does not change build_loader()'s resolution order, it only
    checks that at least one of its branches is actually usable before the
    app starts accepting traffic, instead of only discovering the gap on the
    first document upload.
    """
    if settings.environment != "production":
        return
    if settings.local_doc_dir:
        return
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise StorageConfigurationError(
            "production storage is not configured: set VA_LOCAL_DOC_DIR, or "
            "both VA_SUPABASE_URL and VA_SUPABASE_SERVICE_ROLE_KEY. Without "
            "one of these, build_loader() has no usable backend and every "
            "document upload would fail."
        )


def check_storage_health(settings=None) -> dict:
    """Read-only diagnostic: verifies the configured storage backend is
    reachable, without uploading, downloading, or deleting any object.

    Returns a dict shaped for GET /internal/storage/health — never includes
    the service_role key, a JWT, or any other credential; `details` only
    ever holds non-secret metadata (e.g. the bucket's own public metadata
    fields, which contain no auth material).
    """
    from datetime import datetime, timezone

    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    checked_at = datetime.now(timezone.utc).isoformat()

    if settings.local_doc_dir:
        provider = "local"
        bucket = settings.local_doc_dir
        if not os.path.isdir(settings.local_doc_dir):
            return {
                "provider": provider, "bucket": bucket, "status": "unhealthy",
                "checked_at": checked_at,
                "details": {"reason": "local_doc_dir does not exist"},
            }
        if not os.access(settings.local_doc_dir, os.R_OK | os.W_OK):
            return {
                "provider": provider, "bucket": bucket, "status": "unhealthy",
                "checked_at": checked_at,
                "details": {"reason": "local_doc_dir is not readable/writable"},
            }
        return {
            "provider": provider, "bucket": bucket, "status": "healthy",
            "checked_at": checked_at, "details": {},
        }

    if settings.supabase_url and settings.supabase_service_role_key:
        # Config exists (this branch's guard) and the client below is
        # constructed inline (no persistent state) — the bucket GET is the
        # remaining check: is it actually reachable.
        provider = "supabase"
        bucket = settings.supabase_storage_bucket
        import httpx

        try:
            resp = httpx.get(
                f"{settings.supabase_url.rstrip('/')}/storage/v1/bucket/{bucket}",
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "apikey": settings.supabase_service_role_key,
                },
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            return {
                "provider": provider, "bucket": bucket, "status": "unhealthy",
                "checked_at": checked_at,
                "details": {"reason": f"request to Supabase Storage failed: {type(exc).__name__}"},
            }
        if resp.status_code == 200:
            body = resp.json()
            return {
                "provider": provider, "bucket": bucket, "status": "healthy",
                "checked_at": checked_at,
                "details": {
                    "public": body.get("public"),
                    "created_at": body.get("created_at"),
                },
            }
        return {
            "provider": provider, "bucket": bucket, "status": "unhealthy",
            "checked_at": checked_at,
            "details": {"reason": f"bucket lookup returned HTTP {resp.status_code}"},
        }

    return {
        "provider": "s3", "bucket": settings.s3_bucket, "status": "unknown",
        "checked_at": checked_at,
        "details": {"reason": "health check not implemented for the S3 backend"},
    }
