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

    def load(self, storage_key: str) -> str:
        path = os.path.join(self.base_dir, storage_key)
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def put(self, storage_key: str, data: bytes | str) -> str:
        path = os.path.join(self.base_dir, storage_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = data if isinstance(data, bytes) else data.encode("utf-8")
        with open(path, "wb") as fh:
            fh.write(body)
        return storage_key

    def delete(self, storage_key: str) -> None:
        path = os.path.join(self.base_dir, storage_key)
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
