"""Shared rate limiter instance.

Lives in its own module (not app.main) so routers can import it for
per-route limits (e.g. auth login/signup) without a circular import with
app.main, which wires the limiter into the FastAPI app + middleware.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
