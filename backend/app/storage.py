"""Document content loaders (DocumentLoader implementations).

The worker needs raw document text given a storage_key. Production uses S3
(ap-southeast-2); dev/tests can read from a local directory.
"""
from __future__ import annotations

import os


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


class LocalDocumentLoader:
    """Reads document content from a local directory. For dev/tests only."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def load(self, storage_key: str) -> str:
        path = os.path.join(self.base_dir, storage_key)
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()


def build_loader():
    """Pick a loader from settings: local dir if configured, else S3."""
    from app.config import get_settings

    s = get_settings()
    if s.local_doc_dir:
        return LocalDocumentLoader(s.local_doc_dir)
    return S3DocumentLoader(s.s3_bucket, s.s3_region, s.s3_endpoint_url)
