"""Multi-agent variation-detection scaffold (Google ADK).

Additive, self-contained module — not wired into the production
worker/engine pipeline (see app/worker/job_worker.py, app/engine/). Reads
Project/Document data through the same storage loader the worker uses and
produces output shaped like app/engine/schemas.py's result types, so a
future persistence step would be straightforward. See run.py for the entry
point and orchestrator.py for the agent tree.
"""
from __future__ import annotations
