"""Worker entrypoint:  python -m app.worker

Wires config -> DB session factory -> engine client -> document loader, then
runs the claim/poll/ingest loop forever. Runs as its own process (architecture
decision: separate worker, same image).
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.db import session_factory
from app.engine.client import EngineClient
from app.storage import build_loader
from app.worker.job_worker import run_forever


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("va.worker")
    settings = get_settings()
    loader = build_loader()

    log.info("worker starting; engine=%s db=%s", settings.engine_base_url,
             settings.database_url.split("@")[-1])
    with EngineClient(settings.engine_base_url, api_key=settings.engine_api_key) as client:
        run_forever(session_factory, client, loader, idle_sleep=settings.worker_idle_sleep)


if __name__ == "__main__":
    main()
