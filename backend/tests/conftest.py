"""Test-session environment setup.

Runs before any test module is imported, so required settings (e.g.
VA_JWT_SECRET, which has no insecure default — see app/config.py) are present
before app.main / app.db construct the Settings singleton at import time.
This is a fixed test value, not a real secret — never used outside pytest.
"""
import os

os.environ.setdefault("VA_JWT_SECRET", "test-only-secret-not-for-real-use-1234567890")
