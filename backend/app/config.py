"""Runtime configuration (env-driven).

Centralises the knobs the worker + engine client need. Values come from the
environment / .env. Scope: Australia only -> S3 defaults to ap-southeast-2.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VA_", extra="ignore")

    # Database (product owns all persistence)
    database_url: str = Field(
        default="postgresql+psycopg://localhost/variation_audit",
        description="SQLAlchemy URL for the product Postgres DB",
    )

    # Engine service (stateless; contract v1.1 client target)
    engine_base_url: str = Field(default="http://localhost:8088")
    engine_api_key: str | None = None

    # Object storage (uploaded docs + >1MB result artifacts), AU region
    s3_bucket: str = Field(default="variation-audit-dev")
    s3_region: str = Field(default="ap-southeast-2")          # Sydney — AU residency
    s3_endpoint_url: str | None = None                        # set for MinIO/local
    local_doc_dir: str | None = None                          # dev/test: read docs from disk instead of S3

    # Behaviour
    idempotency_window_days: int = 7                          # decision .21.4
    worker_idle_sleep: float = 2.0

    # Auth (.2) — override jwt_secret in every non-dev environment
    jwt_secret: str = Field(default="dev-only-change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24               # 24h

    # CORS — origins allowed to call the API (the frontend)
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
