"""Real analysis-progress reporting.

`ProgressReporter` is handed to the worker (app/worker/job_worker.py) and
called once after each *major processing step the worker genuinely performs*
— claiming, loading each document, calling the engine, ingesting each
variation/evidence row, finalising. It never synthesises progress: every
field it writes reflects work that actually happened (real processed-document
counts, real variation/evidence counts as rows are created, real elapsed
time). The one derived value is `estimated_remaining`, a straight
extrapolation from real elapsed time and real percent-complete — labelled as
an estimate, not a fabricated event.

Each call appends one `analysis_job_events` row in its *own* short-lived
session, decoupled from the job's transaction, so:
  * events become visible to the SSE endpoint immediately (per-event commit), and
  * an event-write failure can NEVER fail the job — emit() swallows and logs.
"""
from __future__ import annotations

import logging
import time

from app.models import AnalysisJobEvent

logger = logging.getLogger("app.worker.progress")

# The 15 pipeline stages and the percentage each reaches on *completion*.
# Monotonic and derived from real completed steps — not a smooth fake ramp.
STAGE_PCT: dict[str, int] = {
    "Queue": 5,
    "Loading Documents": 15,
    "Parsing Documents": 20,
    "Reading Contract": 26,
    "Reading Scope": 32,
    "Reading RFIs": 38,
    "Reading Emails": 44,
    "AI Analysis": 55,
    "Variation Detection": 68,
    "Evidence Linking": 78,
    "Cost & Time Estimation": 85,
    "Confidence Scoring": 90,
    "Building Report": 95,
    "Finalizing": 98,
    "Completed": 100,
}


class ProgressReporter:
    def __init__(self, session_factory, job, total_documents: int = 0):
        self._sf = session_factory
        self.job_id = job.id
        self._t0 = time.monotonic()
        self.seq = 0
        # running, real counters — updated by the worker as it does the work
        self.total_documents = total_documents
        self.processed_documents = 0
        self.variations_found = 0
        self.evidence_links = 0
        self.current_document: str | None = None
        # remembered so a failure can be attributed to the stage in flight
        self.last_stage = "Queue"
        self.last_pct = 0

    def emit(self, stage: str, status: str, percentage: int, current_document: str | None = None) -> None:
        self.seq += 1
        self.last_stage = stage
        self.last_pct = int(percentage)
        elapsed = time.monotonic() - self._t0
        pct = int(percentage)
        if 0 < pct < 100:
            remaining: float | None = round(elapsed * (100 - pct) / pct, 1)
        elif pct >= 100:
            remaining = 0.0
        else:
            remaining = None
        try:
            with self._sf() as s:
                s.add(AnalysisJobEvent(
                    job_id=self.job_id,
                    seq=self.seq,
                    stage=stage,
                    status=status,
                    percentage=pct,
                    current_document=current_document if current_document is not None else self.current_document,
                    processed_documents=self.processed_documents,
                    total_documents=self.total_documents,
                    variations_found=self.variations_found,
                    evidence_links=self.evidence_links,
                    elapsed_seconds=round(elapsed, 2),
                    estimated_remaining=remaining,
                ))
                s.commit()
        except Exception:  # noqa: BLE001 — progress is auxiliary; never fail the job for it
            logger.warning("progress.emit_failed", extra={"job_id": str(self.job_id), "stage": stage})

    def fail(self) -> None:
        """Emit a terminal failure event against the stage that was in flight."""
        self.emit(self.last_stage, "failed", self.last_pct)

    def cancelled(self) -> None:
        """Emit a terminal 'cancelled' event against the stage in flight."""
        self.emit(self.last_stage, "cancelled", self.last_pct)
