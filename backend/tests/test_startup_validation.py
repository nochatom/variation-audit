"""Unit tests for app.storage.validate_production_storage_config — the
fail-fast-at-startup check for PART 2 of the storage hardening task.

No DB, no network — pure function over a settings-shaped object.
"""
from __future__ import annotations

import pytest

from app.storage import StorageConfigurationError, validate_production_storage_config


class S:
    def __init__(self, environment, local_doc_dir=None, supabase_url=None,
                 supabase_service_role_key=None):
        self.environment = environment
        self.local_doc_dir = local_doc_dir
        self.supabase_url = supabase_url
        self.supabase_service_role_key = supabase_service_role_key


def test_production_with_no_storage_backend_fails_loudly():
    with pytest.raises(StorageConfigurationError):
        validate_production_storage_config(S("production"))


def test_production_with_only_supabase_url_fails():
    with pytest.raises(StorageConfigurationError):
        validate_production_storage_config(S("production", supabase_url="https://x.supabase.co"))


def test_production_with_only_supabase_key_fails():
    with pytest.raises(StorageConfigurationError):
        validate_production_storage_config(S("production", supabase_service_role_key="key"))


def test_production_with_local_doc_dir_passes():
    validate_production_storage_config(S("production", local_doc_dir="/data/docs"))  # must not raise


def test_production_with_full_supabase_config_passes():
    validate_production_storage_config(S(
        "production", supabase_url="https://x.supabase.co", supabase_service_role_key="key",
    ))  # must not raise


def test_development_with_no_storage_backend_does_not_raise():
    """Development behavior must remain unchanged — this is the crux of
    PART 2's "do not affect development" requirement."""
    validate_production_storage_config(S("development"))  # must not raise


def test_unset_environment_defaults_to_non_production_and_does_not_raise():
    validate_production_storage_config(S("staging"))  # anything other than "production" is a no-op
