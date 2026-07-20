"""PostHog analytics client — single shared instance for the product backend.

Initialised at import time from Settings; disabled automatically when no token
is configured (dev/test environments that haven't set VA_POSTHOG_PROJECT_TOKEN).
"""
import atexit

from posthog import Posthog

from app.config import get_settings

_settings = get_settings()

posthog_client = Posthog(
    _settings.posthog_project_token,
    host=_settings.posthog_host,
    enable_exception_autocapture=True,
    disabled=_settings.posthog_disabled or not _settings.posthog_project_token,
)

atexit.register(posthog_client.shutdown)
