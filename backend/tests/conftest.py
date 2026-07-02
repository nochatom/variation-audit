"""Test-session environment setup.

Runs before any test module is imported, so required settings (e.g.
VA_JWT_SECRET, which has no insecure default — see app/config.py) are present
before app.main / app.db construct the Settings singleton at import time.
This is a fixed test value, not a real secret — never used outside pytest.
"""
import os

os.environ.setdefault("VA_JWT_SECRET", "test-only-secret-not-for-real-use-1234567890")

# Rate limiting: the whole suite shares one in-memory limiter keyed to the
# TestClient's fixed client IP, so the production app-wide default would
# accumulate across every test and flake as the suite grows. Relax ONLY the
# default; category limits (auth/uploads/analysis) keep their production
# values so the 429 tests exercise the real numbers (they use limiter.reset()
# for isolation).
os.environ.setdefault("VA_RATE_LIMIT_DEFAULT", "100000/minute")
