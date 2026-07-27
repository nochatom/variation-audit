"""Regression coverage for the free-tier analysis-usage bypass.

Root cause: get_usage()/enforce_analysis_limit() used to count rows in
analysis_jobs, whose project_id FK is ON DELETE CASCADE. Permanently
deleting a project (routers/projects.py:delete_project) deleted that
project's analysis_jobs rows too, silently resetting the org's counted
monthly usage â€” a free org could archive+delete and recreate a project
(the only way to free up Free's 1-project cap) to reset its 5/month analysis
quota indefinitely.

Fix: an immutable analysis_usage_events ledger (app/models.py), written
once per accepted analysis run (app/services/jobs.py:enqueue_analysis) and
never touched by project/job deletion (its FKs are ON DELETE SET NULL, not
CASCADE). enforce_analysis_limit/get_usage now count THIS table. A Postgres
row lock (SELECT ... FOR UPDATE on the org's Subscription) closes the
concurrent-request race between the count-check and the write.
"""
from __future__ import annotations

import uuid

from app.models import AnalysisJob, AnalysisUsageEvent, JobStatus, PlanTier, Subscription, SubscriptionStatus
from app.services import billing as billing_service
from app.services.jobs import enqueue_analysis
from tests.fakes import FakeResult, FakeSession


def _sub(cid, plan=PlanTier.free, status=SubscriptionStatus.active):
    return Subscription(id=uuid.uuid4(), company_id=cid, plan=plan, status=status)


class _RecordingSession(FakeSession):
    """Same canned-result behavior as FakeSession, but also remembers the
    compiled SQL text of every statement passed to execute() â€” lets a test
    assert *which table* a query targeted, and whether it asked for a row
    lock, without needing a real database."""

    def __init__(self, results=None, get_obj=None):
        super().__init__(results=results, get_obj=get_obj)
        self.executed_sql: list[str] = []

    def execute(self, stmt):
        try:
            self.executed_sql.append(str(stmt.compile(compile_kwargs={"literal_binds": False})))
        except Exception:
            self.executed_sql.append(repr(stmt))
        return super().execute(stmt)


# ---------------------------------------------------------------------------
# 1. enqueue_analysis writes an immutable usage-ledger row alongside the job
# ---------------------------------------------------------------------------
def test_enqueue_analysis_records_a_usage_event():
    session = FakeSession(results=[FakeResult(scalar=None)])  # idempotency lookup: no existing job
    cid, pid = uuid.uuid4(), uuid.uuid4()

    job = enqueue_analysis(session, company_id=cid, project_id=pid, created_by=uuid.uuid4())

    events = session.added_of(AnalysisUsageEvent)
    assert len(events) == 1
    assert events[0].company_id == cid
    assert events[0].project_id == pid
    assert events[0].job_id == job.id
    assert job.status == JobStatus.queued


def test_enqueue_analysis_idempotent_replay_does_not_double_charge():
    """A replayed request_id returns the existing job (no new AnalysisJob
    row) â€” it must also not write a second usage event, or a client retry
    would cost the org two units of quota for one accepted run."""
    from datetime import datetime, timezone

    cid, pid, rid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    existing = AnalysisJob()
    existing.company_id, existing.project_id, existing.request_id = cid, pid, rid
    existing.created_at = datetime.now(timezone.utc)
    existing.status = JobStatus.queued
    session = FakeSession(results=[FakeResult(scalar=existing)])

    job = enqueue_analysis(session, company_id=cid, project_id=pid, request_id=rid)

    assert job is existing
    assert session.added_of(AnalysisUsageEvent) == []
    assert session.commits == 0


# ---------------------------------------------------------------------------
# 2. enforce_analysis_limit / get_usage count the ledger, not analysis_jobs
#    (the actual bypass: analysis_jobs rows vanish with their project;
#    analysis_usage_events rows don't)
# ---------------------------------------------------------------------------
def test_enforce_analysis_limit_queries_the_usage_ledger_not_analysis_jobs():
    cid = uuid.uuid4()
    session = _RecordingSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),  # locked subscription lookup
        FakeResult(scalar=4),                              # COUNT: 4 usage events, under the cap of 5
    ])
    billing_service.enforce_analysis_limit(session, cid)

    count_query = session.executed_sql[1]
    assert "analysis_usage_events" in count_query
    assert "analysis_jobs" not in count_query


def test_get_usage_analysis_runs_queries_the_usage_ledger_not_analysis_jobs():
    cid = uuid.uuid4()
    session = _RecordingSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),  # get_or_create_subscription
        FakeResult(scalar=2),                              # COUNT: documents_processed
        FakeResult(scalar=1),                              # COUNT: analysis_runs
        FakeResult(scalar=0),                              # COUNT: projects_active
    ])
    usage = billing_service.get_usage(session, cid)

    analysis_query = session.executed_sql[2]
    assert "analysis_usage_events" in analysis_query
    assert "analysis_jobs" not in analysis_query
    assert usage["analysis_runs"] == 1
    assert usage["analysis_runs_limit"] == 5


def test_project_deletion_cascade_cannot_touch_the_usage_ledger():
    """Documents the actual fix, structurally: analysis_usage_events'
    project_id/job_id FKs are ON DELETE SET NULL, never CASCADE â€” unlike
    analysis_jobs.project_id (CASCADE), deleting a Project can only null out
    the reference on a usage-event row, never delete the row itself, so the
    monthly count it contributes to can never go down."""
    from app.models import AnalysisJob as _AnalysisJob

    usage_event_project_fk = AnalysisUsageEvent.__table__.c.project_id.foreign_keys
    job_project_fk = _AnalysisJob.__table__.c.project_id.foreign_keys

    (usage_fk,) = usage_event_project_fk
    (job_fk,) = job_project_fk

    assert usage_fk.ondelete == "SET NULL"
    assert job_fk.ondelete == "CASCADE"


# ---------------------------------------------------------------------------
# 3. Concurrent-request race: the subscription lookup takes a row lock
# ---------------------------------------------------------------------------
def test_enforce_analysis_limit_locks_the_subscription_row():
    cid = uuid.uuid4()
    session = _RecordingSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalar=4),
    ])
    billing_service.enforce_analysis_limit(session, cid)

    subscription_query = session.executed_sql[0]
    assert "subscriptions" in subscription_query
    assert "FOR UPDATE" in subscription_query


# ---------------------------------------------------------------------------
# 4. End-to-end: quota is enforced at the cap regardless of how many
#    analysis_jobs rows currently exist (i.e. even right after a project delete)
# ---------------------------------------------------------------------------
def test_enforce_analysis_limit_blocks_at_cap_using_ledger_count():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalar=5),  # COUNT: already 5 ledger rows == the Free cap
    ])
    try:
        billing_service.enforce_analysis_limit(session, cid)
        assert False, "expected PlanLimitExceeded"
    except billing_service.PlanLimitExceeded as exc:
        assert exc.code == "analysis_limit_exceeded"
