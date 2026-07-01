"""Structured (JSON) logging — one JSON object per line to stdout.

Suitable for ingestion by any log aggregator/SIEM (CloudWatch, Datadog, ELK,
etc.) without a separate parsing step. Call configure_logging() once at
startup (app.main does this at import time).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# Fields every LogRecord already carries that we don't want to re-dump verbatim
# (avoids duplicating info already surfaced via `message`/`level`/etc.).
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Anything passed via logger.info(..., extra={...}) rides along as its
        # own top-level JSON field — e.g. event, user_id, status_code, path.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


# security-relevant events funnel through this named logger, so they're
# trivially filterable in aggregated logs (logger == "va.security").
security_logger = logging.getLogger("va.security")
