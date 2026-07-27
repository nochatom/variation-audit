"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import Link from "next/link";
import { api, API_BASE, getToken, ProjectDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { billingApi, Usage } from "@/lib/billing/api";
import { FreeUsageMeter } from "@/components/billing/FreeUsageMeter";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState, aud } from "@/components/ui";

/* ------------------------------------------------------------------ *
 * Analysis run dashboard.
 * While a job is queued/running, EVERY live value — progress %, current
 * step, elapsed/remaining, document/variation/evidence counts and each
 * technical stage — comes from the backend Server-Sent Events stream
 * (GET /projects/{id}/analysis/{jobId}/events). Nothing about in-flight
 * progress is fabricated on the client, and there is no polling: the stream
 * pushes, we render. When there is no live job (idle / already-finished),
 * the panel shows the persisted terminal state from the dashboard.
 * Visual register: GitHub Actions / Stripe / Codex.
 * ------------------------------------------------------------------ */

const STEPS = ["Uploading documents", "AI analysis", "Detecting variations", "Preparing report"] as const;

type StepState = "done" | "active" | "pending" | "error";
type RunState = "idle" | "queued" | "running" | "done" | "error" | "cancelled";

/* ---------------- technical-detail stages ---------------- *
 * The 15 stages the worker actually emits (app/worker/progress.py). Each
 * stage's live state is taken verbatim from the backend event whose `stage`
 * matches — never inferred. `phase` aligns each stage with the four
 * high-level steps for the summary pipeline.
 */
type StageState = "pending" | "running" | "completed" | "failed";
const TECH_STAGES: { name: string; phase: number }[] = [
  { name: "Queue", phase: 0 },
  { name: "Loading Documents", phase: 0 },
  { name: "Parsing Documents", phase: 0 },
  { name: "Reading Contract", phase: 0 },
  { name: "Reading Scope", phase: 0 },
  { name: "Reading RFIs", phase: 0 },
  { name: "Reading Emails", phase: 0 },
  { name: "AI Analysis", phase: 1 },
  { name: "Variation Detection", phase: 2 },
  { name: "Evidence Linking", phase: 2 },
  { name: "Cost & Time Estimation", phase: 2 },
  { name: "Confidence Scoring", phase: 2 },
  { name: "Building Report", phase: 3 },
  { name: "Finalizing", phase: 3 },
  { name: "Completed", phase: 4 },
];
const STAGE_PHASE: Record<string, number> = Object.fromEntries(
  TECH_STAGES.map((s) => [s.name, s.phase]),
);

/* ---------------- backend progress event ---------------- *
 * Exact field set emitted by the SSE endpoint (Task 3). */
type ProgressEvent = {
  seq: number;
  stage: string;
  status: string; // "running" | "completed" | "failed"
  percentage: number;
  current_document: string | null;
  processed_documents: number;
  total_documents: number;
  variations_found: number;
  evidence_links: number;
  elapsed_seconds: number;
  estimated_remaining: number | null;
};

function fmtDur(ms: number | null): string {
  if (ms == null || ms < 0) return "—";
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

// A run is considered stalled if no progress event arrives for this long.
const STALL_MS = 60_000;

const TERMINAL_STAGE = "Completed";
const isTerminal = (e: ProgressEvent) =>
  e.status === "failed" || e.status === "cancelled" || e.stage === TERMINAL_STAGE || e.percentage >= 100;

/* ---------------- live log ---------------- */
type LogEntry = { id: number; time: string; msg: string; kind: string };
const MAX_LOG = 500;

function clock(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

// Human-readable line for one backend event — informative, but strictly
// derived from the event's real fields (nothing invented).
function eventMessage(e: ProgressEvent): string {
  if (e.status === "failed") return `${e.stage} failed`;
  if (e.status === "running") return e.current_document ? `${e.stage}: ${e.current_document}` : `${e.stage} started`;
  const extra =
    e.stage === "Loading Documents" ? ` (${e.processed_documents}/${e.total_documents})`
    : e.stage === "Variation Detection" ? ` (${e.variations_found} found)`
    : e.stage === "Evidence Linking" ? ` (${e.evidence_links} linked)`
    : "";
  return `${e.stage} completed${extra}`;
}

/* ------------------------------------------------------------------ *
 * useAnalysisStream — subscribe to one job's live progress over SSE.
 *
 * Opens an EventSource while `active` (job queued/running). The token rides
 * as a query param because EventSource can't set an Authorization header;
 * the backend accepts either. On connect the backend replays every event
 * from seq 0, so a late-joining client gets the full stage history. The last
 * event is retained after the stream closes so final stats stay on screen.
 * `onEnd` fires once when the run reaches a terminal event so the caller can
 * refresh the dashboard for persisted totals. No polling anywhere.
 * ------------------------------------------------------------------ */
function useAnalysisStream(
  projectId: string | null,
  jobId: string | null,
  active: boolean,
  onEnd: () => void,
) {
  const [live, setLive] = useState<ProgressEvent | null>(null);
  const [stages, setStages] = useState<Record<string, StageState>>({});
  const [connected, setConnected] = useState(false);
  const [stalled, setStalled] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const onEndRef = useRef(onEnd);
  onEndRef.current = onEnd;
  const logIdRef = useRef(0);
  const lastSeqRef = useRef(0);
  const lastEventAtRef = useRef(0); // wall-clock of the last real event received
  const lastLoggedRef = useRef(""); // stage|status|doc of the last LOGGED event (dedup heartbeats)

  const pushLog = useCallback((msg: string, kind: string) => {
    setLog((prev) => {
      const entry: LogEntry = { id: logIdRef.current++, time: clock(), msg, kind };
      // Ring buffer: never keep more than MAX_LOG entries.
      const next = prev.length >= MAX_LOG ? prev.slice(prev.length - (MAX_LOG - 1)) : prev.slice();
      next.push(entry);
      return next;
    });
  }, []);

  // Reset accumulated state whenever the job we're watching changes.
  useEffect(() => {
    setLive(null);
    setStages({});
    setConnected(false);
    setStalled(false);
    setLog([]);
    lastSeqRef.current = 0;
    lastEventAtRef.current = 0;
    lastLoggedRef.current = "";
  }, [jobId]);

  useEffect(() => {
    if (!active || !projectId || !jobId) return;
    const token = getToken();
    if (!token) return;

    const url = `${API_BASE}/projects/${projectId}/analysis/${jobId}/events?access_token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    let ended = false;
    lastEventAtRef.current = Date.now();

    const finish = () => {
      if (ended) return;
      ended = true;
      es.close();
      clearInterval(stallTimer);
      setConnected(false);
      onEndRef.current();
    };

    // Mark an event as just-received: clears any stall and restarts the clock.
    const gotSignal = () => {
      lastEventAtRef.current = Date.now();
      setStalled(false);
    };

    es.onopen = () => {
      setConnected(true);
      gotSignal();
      pushLog("Connected — streaming live progress", "meta");
    };
    es.addEventListener("progress", (ev) => {
      let e: ProgressEvent;
      try {
        e = JSON.parse((ev as MessageEvent).data);
      } catch {
        return;
      }
      gotSignal();
      setLive((prev) => (prev && prev.seq > e.seq ? prev : e)); // monotonic by seq
      setStages((prev) => ({ ...prev, [e.stage]: e.status as StageState }));
      if (e.seq > lastSeqRef.current) {
        lastSeqRef.current = e.seq;
        // Dedup repeated heartbeats: a long stage (AI Analysis) re-emits the
        // same running event every poll to keep the stream alive — log it once,
        // not once per poll. Per-document loading keeps distinct lines via the
        // current_document part of the key.
        const key = `${e.stage}|${e.status}|${e.current_document ?? ""}`;
        if (key !== lastLoggedRef.current) {
          lastLoggedRef.current = key;
          pushLog(eventMessage(e), e.status); // one timestamped log line per distinct backend event
        }
      }
      if (isTerminal(e)) finish();
    });
    es.addEventListener("end", finish);
    es.onerror = () => {
      // EventSource auto-reconnects (resuming via Last-Event-ID). If the job
      // is already terminal the backend closes immediately — treat a closed
      // connection as the end so we don't spin reconnecting forever.
      if (es.readyState === EventSource.CLOSED) finish();
    };

    // Real stall detection: flag a stall only when NO event has actually
    // arrived for STALL_MS. Measured against real event arrival times — never
    // a fabricated timeout.
    const stallTimer = setInterval(() => {
      if (ended) return;
      if (Date.now() - lastEventAtRef.current >= STALL_MS) setStalled(true);
    }, 2000);

    return () => {
      ended = true;
      es.close();
      clearInterval(stallTimer);
    };
  }, [projectId, jobId, active]);

  return { live, stages, connected, stalled, log };
}

export default function AnalysisPage() {
  const { companyId } = useApp();
  const [rows, setRows] = useState<ProjectDashboard[] | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // `load` is the single refresh path for this page — it's called on mount,
  // right after a run/cancel request is accepted, AND as the SSE stream's
  // onEnd callback the moment a job reaches a terminal event (see
  // useAnalysisStream below). Fetching usage here alongside the dashboard
  // means the quota meter updates immediately after every completed
  // analysis, always from the backend's own count (never computed
  // client-side) — the backend stays the sole source of truth, the frontend
  // only re-displays what it returns.
  const load = useCallback(async () => {
    if (!companyId) return;
    const [dash, freshUsage] = await Promise.all([
      api.orgDashboard(companyId),
      billingApi.getUsage(companyId).catch(() => null),
    ]);
    const details = await Promise.all(dash.projects.map((p) => api.projectDashboard(p.id).catch(() => null)));
    const list = details.filter((d): d is ProjectDashboard => d !== null);
    setRows(list);
    setSelectedId((cur) => cur ?? list[0]?.project.id ?? null);
    if (freshUsage) setUsage(freshUsage);
  }, [companyId]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  const [cancelling, setCancelling] = useState(false);

  async function run(projectId: string) {
    setRunning(projectId);
    setError(null);
    try {
      await api.analyze(projectId);
      setSelectedId(projectId);
      await load(); // pick up the new queued job id, which arms the SSE stream
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(null);
    }
  }

  async function cancel(projectId: string, jobId: string) {
    setCancelling(true);
    setError(null);
    try {
      await api.cancelAnalysis(projectId, jobId);
      await load(); // reflect the new status; the SSE also delivers a cancelled event
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCancelling(false);
    }
  }

  const selected = useMemo(() => rows?.find((d) => d.project.id === selectedId) ?? null, [rows, selectedId]);

  // Stream the selected project's latest job while it is queued/running.
  const jobId = selected?.latest_job?.id ?? null;
  const jobStatus = selected?.latest_job?.status ?? null;
  const streamActive = jobStatus === "queued" || jobStatus === "running";
  const { live, stages, connected, stalled, log } = useAnalysisStream(
    selected?.project.id ?? null,
    jobId,
    streamActive,
    load,
  );

  return (
    <div>
      <PageHeader
        title="Analysis"
        description="Run AI detection on a project's record and watch each stage of the pipeline stream live."
      />
      {error && <ErrorNote message={error} />}
      {!rows && !error && <Spinner />}

      {rows && rows.length === 0 && (
        <EmptyState title="No projects to analyze" body="Create a project and ingest documents first." />
      )}

      {rows && rows.length > 0 && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <RunPanel
            d={selected}
            live={live}
            stages={stages}
            log={log}
            stalled={stalled && streamActive}
            streamActive={streamActive}
            connected={connected}
            busy={selected ? running === selected.project.id : false}
            cancelling={cancelling}
            quotaExhausted={!!usage && usage.analysis_runs_limit != null && usage.analysis_runs >= usage.analysis_runs_limit}
            onRun={() => selected && run(selected.project.id)}
            onCancel={() => {
              if (selected?.latest_job) cancel(selected.project.id, selected.latest_job.id);
            }}
          />
          <div className="flex flex-col gap-4">
            {usage && <FreeUsageMeter usage={usage} />}
            <ProjectRail
              rows={rows}
              selectedId={selectedId}
              runningId={running}
              livePct={live && streamActive ? live.percentage : null}
              onSelect={setSelectedId}
              onRun={run}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * View model — one source of truth for what the panel renders.
 * `fromLive` uses ONLY backend event fields. `fromStatus` is the truthful
 * terminal/idle view derived from the persisted job status (no in-flight
 * fabrication — a finished job is 100%, an idle one is 0%).
 * ------------------------------------------------------------------ */
type VM = {
  state: RunState;
  pct: number;
  label: string;
  steps: StepState[];
  stageStates: StageState[];
  completedStages: number;
  elapsedMs: number | null;
  remainingMs: number | null;
  currentStatus: string;
  docsProcessed: string;
  variations: string;
  evidence: string;
  source: "live" | "terminal" | "idle" | "starting" | "queued" | "cancelled";
};

function stepsFor(state: RunState, activePhase: number): StepState[] {
  return STEPS.map((_, i) => {
    if (state === "done") return "done";
    if (state === "error") return i < activePhase ? "done" : i === activePhase ? "error" : "pending";
    // Cancelled: freeze progress — steps completed so far stay done, the rest
    // pending, and nothing is left spinning (no "active").
    if (state === "cancelled") return i < activePhase ? "done" : "pending";
    if (state === "running") return i < activePhase ? "done" : i === activePhase ? "active" : "pending";
    return "pending";
  });
}

function fromLive(e: ProgressEvent, stages: Record<string, StageState>): VM {
  const cancelled = e.status === "cancelled";
  const failed = e.status === "failed";
  const done = !failed && !cancelled && (e.stage === TERMINAL_STAGE || e.percentage >= 100);
  const state: RunState = cancelled ? "cancelled" : failed ? "error" : done ? "done" : "running";
  const activePhase = Math.min(STAGE_PHASE[e.stage] ?? 0, STEPS.length - 1);
  const stageStates = TECH_STAGES.map((s) => stages[s.name] ?? "pending");
  return {
    state,
    pct: e.percentage,
    label: e.stage,
    steps: stepsFor(state, activePhase),
    stageStates,
    completedStages: stageStates.filter((s) => s === "completed").length,
    elapsedMs: e.elapsed_seconds * 1000,
    remainingMs: e.estimated_remaining != null ? e.estimated_remaining * 1000 : null,
    currentStatus: e.current_document ? `${e.stage} — ${e.current_document}` : e.stage,
    docsProcessed: `${e.processed_documents}/${e.total_documents}`,
    variations: String(e.variations_found),
    evidence: String(e.evidence_links),
    source: "live",
  };
}

function fromStatus(d: ProjectDashboard): VM {
  const status = d.latest_job?.status ?? null;

  // Queued: the backend has NOT started work yet. Never fabricate an
  // "Uploading documents" stage — say honestly it's waiting for a worker.
  if (status === "queued") {
    return {
      state: "queued", pct: 0, label: "Queued — waiting for an available worker",
      steps: STEPS.map(() => "pending"),
      stageStates: TECH_STAGES.map(() => "pending"),
      completedStages: 0,
      elapsedMs: null, remainingMs: null, currentStatus: "Queued",
      docsProcessed: "—", variations: "—", evidence: "—", source: "queued",
    };
  }

  // Running but the first SSE event hasn't landed yet (momentary window after
  // a worker claims the job): truthful "starting" — no invented stage/percent,
  // no step marked active until a real event says so.
  if (status === "running") {
    return {
      state: "running", pct: 0, label: "Starting…",
      steps: STEPS.map(() => "pending"),
      stageStates: TECH_STAGES.map(() => "pending"),
      completedStages: 0,
      elapsedMs: null, remainingMs: null, currentStatus: "Starting…",
      docsProcessed: "—", variations: "—", evidence: "—", source: "starting",
    };
  }

  // Cancelled: a terminal state — stopped by the user, no progress fabricated.
  if (status === "cancelled") {
    return {
      state: "cancelled", pct: 0, label: "Cancelled",
      steps: STEPS.map(() => "pending"),
      stageStates: TECH_STAGES.map(() => "pending"),
      completedStages: 0,
      elapsedMs: null, remainingMs: null, currentStatus: "Cancelled by user",
      docsProcessed: String(d.document_count), variations: String(d.counts.total),
      evidence: "—", source: "cancelled",
    };
  }

  const done = status === "succeeded" || status === "completed";
  const failed = status === "failed";
  const state: RunState = done ? "done" : failed ? "error" : "idle";
  return {
    state,
    pct: done ? 100 : 0,
    label: done ? "Completed" : failed ? "Failed" : "Not started",
    steps: stepsFor(state, failed ? STEPS.length - 1 : 0),
    stageStates: TECH_STAGES.map(() => (done ? "completed" : "pending")),
    completedStages: done ? TECH_STAGES.length : 0,
    elapsedMs: null,
    remainingMs: null,
    currentStatus: done ? "Completed" : failed ? "Failed" : "Not started",
    docsProcessed: String(d.document_count),
    variations: String(d.counts.total),
    evidence: "—",
    source: state === "idle" ? "idle" : "terminal",
  };
}

/* ---------------- failure / stall banners ---------------- */
function StallBanner({ busy, onRetry, onViewLogs }: { busy: boolean; onRetry: () => void; onViewLogs: () => void }) {
  return (
    <div role="alert" className="mt-5 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-500/30 dark:bg-amber-500/10">
      <div className="flex items-start gap-3">
        <svg viewBox="0 0 24 24" className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
        </svg>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-bold text-ip-ink">Analysis appears stalled.</p>
          <p className="mt-0.5 text-[12.5px] leading-relaxed text-ip-ink-2">
            No progress event has been received for over {STALL_MS / 1000} seconds. The worker may have stopped or lost connection.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={onRetry} disabled={busy} className="btn-orange text-xs">
              {busy ? "Retrying…" : "Retry Analysis"}
            </button>
            <button onClick={onViewLogs} className="rounded-md border border-ip-line px-3 py-1.5 text-xs font-semibold text-ip-ink-2 transition-colors hover:bg-ip-card-2">
              View Logs
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FailureBanner({
  stage, code, message, retryable, busy, onRetry,
}: {
  stage: string | null;
  code: string | null;
  message: string | null;
  retryable: boolean | null | undefined;
  busy: boolean;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="mt-5 rounded-lg border border-ip-risk/30 bg-ip-risk/[0.06] p-4">
      <div className="flex items-start gap-3">
        <svg viewBox="0 0 24 24" className="mt-0.5 h-5 w-5 shrink-0 text-ip-risk" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" />
        </svg>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-bold text-ip-risk">Analysis failed</p>
          {stage && (
            <p className="mt-0.5 text-[12.5px] text-ip-ink-2">
              Failed stage: <span className="font-semibold text-ip-ink">{stage}</span>
            </p>
          )}
          <p className="mt-1 break-words text-[12.5px] leading-relaxed text-ip-ink-2">
            {code && <span className="font-mono font-semibold text-ip-ink">{code}: </span>}
            {message || "The analysis job reported a failure."}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <button onClick={onRetry} disabled={busy} className="btn-orange text-xs">
              {busy ? "Retrying…" : "Retry Analysis"}
            </button>
            {retryable === false && (
              <span className="text-[11px] font-medium text-ip-ink-3">This error is unlikely to resolve on retry.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------- confirm-stop dialog ---------------- */
function ConfirmStopDialog({ busy, onConfirm, onDismiss }: { busy: boolean; onConfirm: () => void; onDismiss: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onDismiss(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  return (
    <div className="fixed inset-0 z-40 grid place-items-center p-4">
      <div className="absolute inset-0 bg-ip-navy/30 backdrop-blur-[1px]" onClick={onDismiss} aria-hidden />
      <div role="dialog" aria-modal="true" aria-labelledby="stop-title"
           className="animate-scale-in relative w-full max-w-sm rounded-lg border border-ip-line bg-ip-card p-5 shadow-ip-pop">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ip-risk/12 text-ip-risk">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" /></svg>
          </span>
          <div className="min-w-0">
            <h3 id="stop-title" className="text-[15px] font-bold text-ip-ink">Are you sure you want to stop this analysis?</h3>
            <p className="mt-1 text-[13px] leading-relaxed text-ip-ink-2">
              Progress so far will be discarded and the run marked <span className="font-semibold">Cancelled</span>. You can start a new analysis at any time.
            </p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onDismiss} disabled={busy}
                  className="rounded-md border border-ip-line px-3.5 py-2 text-sm font-semibold text-ip-ink-2 transition-colors hover:bg-ip-card-2 disabled:opacity-60">
            Keep running
          </button>
          <button onClick={onConfirm} disabled={busy}
                  className="rounded-md bg-ip-risk px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-ip-risk/90 disabled:opacity-60">
            {busy ? "Stopping…" : "Stop analysis"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- run panel (hero) ---------------- */
function RunPanel({
  d, live, stages, log, stalled, streamActive, connected, busy, cancelling, quotaExhausted, onRun, onCancel,
}: {
  d: ProjectDashboard | null;
  live: ProgressEvent | null;
  stages: Record<string, StageState>;
  log: LogEntry[];
  stalled: boolean;
  streamActive: boolean;
  connected: boolean;
  busy: boolean;
  cancelling: boolean;
  quotaExhausted: boolean;
  onRun: () => void;
  onCancel: () => void;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  const viewLogs = () => logRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });

  if (!d) return <Card className="grid place-items-center p-16 text-sm text-ip-ink-3">Select a project to view its analysis run.</Card>;

  // Live event wins whenever we have one (including the retained final event);
  // otherwise fall back to the persisted status — never a fabricated ramp.
  const vm = live ? fromLive(live, stages) : fromStatus(d);

  // The Stop button shows only while the job is actively processing.
  const active = vm.state === "queued" || vm.state === "running";

  // Failure detail — the stage from the real "failed" event (kept in `live`/
  // `stages`), the message/code from the persisted job row.
  const failed = vm.state === "error";
  const failedStage =
    live?.status === "failed" ? live.stage
    : (Object.entries(stages).find(([, s]) => s === "failed")?.[0] ?? null);
  const errorCode = d.latest_job?.error_code ?? null;
  const errorMessage = d.latest_job?.error_message ?? null;
  const retryable = d.latest_job?.error_retryable;

  return (
    <Card className="p-6">
      {/* header row */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="ip-label">Analysis run</div>
          <Link
            href={`/app/projects/${d.project.id}`}
            className="mt-1 block truncate text-[19px] font-bold tracking-tight text-ip-ink hover:text-ip-navy"
          >
            {d.project.name}
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <RunStateBadge state={vm.state} live={vm.source === "live" || vm.source === "starting"} connected={connected} />
          {active ? (
            <button
              onClick={() => setConfirmStop(true)}
              disabled={cancelling}
              className="inline-flex items-center gap-1.5 rounded-md border border-ip-risk/40 px-3.5 py-2 text-sm font-semibold text-ip-risk transition-colors hover:bg-ip-risk/[0.06] disabled:opacity-60"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor" aria-hidden><rect x="6" y="6" width="12" height="12" rx="1.5" /></svg>
              {cancelling ? "Stopping…" : "Stop Analysis"}
            </button>
          ) : (
            <button
              onClick={onRun}
              disabled={busy || quotaExhausted}
              title={quotaExhausted ? "Monthly analysis quota reached — upgrade to run more." : undefined}
              className="btn-orange disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Queuing…" : quotaExhausted ? "Quota reached" : vm.state === "idle" ? "Run analysis" : "Re-run"}
            </button>
          )}
        </div>
      </div>

      {confirmStop && (
        <ConfirmStopDialog
          busy={cancelling}
          onConfirm={() => { onCancel(); setConfirmStop(false); }}
          onDismiss={() => setConfirmStop(false)}
        />
      )}

      {/* failure takes precedence over a stall warning */}
      {failed ? (
        <FailureBanner
          stage={failedStage}
          code={errorCode}
          message={errorMessage}
          retryable={retryable}
          busy={busy}
          onRetry={onRun}
        />
      ) : stalled ? (
        <StallBanner busy={busy} onRetry={onRun} onViewLogs={viewLogs} />
      ) : null}

      {/* progress bar + percentage */}
      <div className="mt-6">
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="text-[13px] font-medium text-ip-ink-2">{vm.label}</span>
          <span className="text-[13px] font-bold tabular-nums text-ip-ink">{vm.pct}%</span>
        </div>
        <ProgressBar pct={vm.pct} state={vm.state} />
      </div>

      {/* four-step pipeline */}
      <ol className="mt-6 space-y-1">
        {STEPS.map((label, i) => (
          <Step key={label} n={i + 1} label={label} state={vm.steps[i]} last={i === STEPS.length - 1} />
        ))}
      </ol>

      {/* metrics grid — every value below is a real backend figure while live */}
      <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-ip-line bg-ip-line sm:grid-cols-3">
        <Metric label="Elapsed" value={fmtDur(vm.elapsedMs)} mono />
        <Metric label="Est. remaining" value={fmtDur(vm.remainingMs)} mono />
        <Metric label="Current status" value={vm.currentStatus} />
        <Metric label="Documents processed" value={vm.docsProcessed} mono />
        <Metric label="Variations detected" value={vm.variations} mono />
        <Metric label="Evidence collected" value={vm.evidence} mono />
      </div>

      {log.length > 0 && <LogWindow entries={log} live={streamActive && connected} scrollRef={logRef} />}

      <TechnicalDetails vm={vm} />
    </Card>
  );
}

/* ---------------- pieces ---------------- */
function RunStateBadge({ state, live, connected }: { state: RunState; live: boolean; connected: boolean }) {
  if (state === "queued") return <Chip tone="navy">Queued</Chip>;
  if (state === "running")
    return (
      <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ip-navy">
        <Spin /> {live && connected ? "Live" : "In progress"}
      </span>
    );
  if (state === "done") return <Chip tone="recovery">Completed</Chip>;
  if (state === "error") return <Chip tone="risk">Failed</Chip>;
  if (state === "cancelled") return <Chip tone="neutral">Cancelled</Chip>;
  return <span className="text-[13px] font-medium text-ip-ink-3">Idle</span>;
}

function ProgressBar({ pct, state }: { pct: number; state: RunState }) {
  const color =
    state === "error" ? "bg-ip-risk" : state === "done" ? "bg-ip-recovery"
    : state === "cancelled" ? "bg-ip-ink-3" : "bg-ip-navy";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-ip-card-3">
      <div
        className={`h-full rounded-full ${color} transition-[width] duration-500 ease-out`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function Step({ n, label, state, last }: { n: number; label: string; state: StepState; last: boolean }) {
  return (
    <li className="relative flex items-center gap-3 py-1.5">
      {!last && (
        <span
          className={`absolute left-[11px] top-8 h-[calc(100%-16px)] w-px ${state === "done" ? "bg-ip-recovery/40" : "bg-ip-line"}`}
          aria-hidden
        />
      )}
      <span className="relative grid h-6 w-6 shrink-0 place-items-center rounded-full">
        {state === "done" ? (
          <span className="grid h-6 w-6 place-items-center rounded-full bg-ip-recovery/12 text-ip-recovery">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
          </span>
        ) : state === "active" ? (
          <span className="grid h-6 w-6 place-items-center rounded-full bg-ip-navy/10 text-ip-navy"><Spin /></span>
        ) : state === "error" ? (
          <span className="grid h-6 w-6 place-items-center rounded-full bg-ip-risk/12 text-ip-risk">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </span>
        ) : (
          <span className="h-2 w-2 rounded-full bg-ip-line-strong" />
        )}
      </span>
      <span className={`text-[14px] ${state === "pending" ? "font-medium text-ip-ink-3" : state === "error" ? "font-semibold text-ip-risk" : "font-semibold text-ip-ink"}`}>
        {n}. {label}
      </span>
      {state === "active" && <span className="ip-label ml-auto text-ip-navy">running</span>}
    </li>
  );
}

function Metric({ label, value, mono, hint }: { label: string; value: string; mono?: boolean; hint?: string }) {
  return (
    <div className="bg-ip-card p-4">
      <div className="ip-label flex items-center gap-1.5">
        {label}
        {hint && <span className="rounded-pill bg-ip-card-3 px-1.5 py-px text-[9px] font-semibold normal-case tracking-normal text-ip-ink-3">{hint}</span>}
      </div>
      <div className={`mt-1.5 truncate text-[20px] font-bold leading-none text-ip-ink ${mono ? "tabular-nums" : ""}`}>{value}</div>
    </div>
  );
}

/* ---------------- live log window ---------------- *
 * One timestamped line per backend event (capped at MAX_LOG in the hook).
 * Auto-scrolls to the newest entry while the viewer is pinned to the bottom;
 * scrolling up to read history pauses the auto-scroll until they return. */
const LOG_KIND_CLS: Record<string, string> = {
  completed: "text-ip-recovery",
  running: "text-amber-500",
  failed: "text-ip-risk",
  meta: "text-ip-ink-3",
};

function LogWindow({ entries, live, scrollRef }: { entries: LogEntry[]; live: boolean; scrollRef?: RefObject<HTMLDivElement | null> }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    if (pinned && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [entries, pinned]);

  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
  };

  return (
    <div className="mt-6" ref={scrollRef}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="ip-label">Live log</span>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-ip-ink-3">
          {live && <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-ip-recovery" />}
          <span className="tabular-nums">{entries.length}</span>
          <span>/ {MAX_LOG}</span>
        </span>
      </div>
      <div
        ref={ref}
        onScroll={onScroll}
        role="log"
        aria-live="polite"
        aria-label="Live analysis log"
        className="h-48 overflow-y-auto rounded-lg border border-ip-line bg-ip-ink/[0.96] p-3 font-mono text-[12px] leading-relaxed"
      >
        {entries.map((e) => (
          <div key={e.id} className="flex gap-2 whitespace-pre-wrap break-words">
            <span className="shrink-0 tabular-nums text-ip-ink-3/80">[{e.time}]</span>
            <span className={LOG_KIND_CLS[e.kind] ?? "text-ip-card"}>{e.msg}</span>
          </div>
        ))}
      </div>
      {!pinned && (
        <button
          onClick={() => setPinned(true)}
          className="mt-1.5 text-[11px] font-semibold text-ip-navy hover:underline"
        >
          ↓ Jump to newest
        </button>
      )}
    </div>
  );
}

function TechnicalDetails({ vm }: { vm: VM }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-6 border-t border-ip-line pt-4">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-[13px] font-semibold text-ip-ink-2 transition-colors hover:text-ip-ink"
      >
        <svg viewBox="0 0 24 24" className={`h-4 w-4 transition-transform duration-150 ease-out ${open ? "rotate-90" : ""}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
        Show technical details
        <span className="ip-label ml-auto normal-case tracking-normal text-ip-ink-3">
          {vm.completedStages}/{TECH_STAGES.length}
        </span>
      </button>
      {open && (
        <div className="mt-3 overflow-hidden rounded-lg border border-ip-line bg-ip-card-2">
          <ol className="divide-y divide-ip-line/60">
            {TECH_STAGES.map((s, i) => (
              <TechRow key={s.name} name={s.name} state={vm.stageStates[i]} />
            ))}
          </ol>
          <p className="border-t border-ip-line px-3 py-2 text-[11px] leading-relaxed text-ip-ink-3">
            {vm.source === "live" || vm.source === "starting"
              ? "Live stage events streamed from the backend as each step is reached — nothing here is simulated."
              : vm.source === "terminal"
              ? "Final stage states from the completed job."
              : "No run yet — stages activate once analysis starts."}
          </p>
        </div>
      )}
    </div>
  );
}

const STAGE_UI: Record<StageState, { dotCls: string; textCls: string; label: string; labelCls: string }> = {
  completed: { dotCls: "bg-ip-recovery", textCls: "text-ip-ink", label: "completed", labelCls: "text-ip-recovery" },
  running:   { dotCls: "bg-amber-400", textCls: "text-ip-ink", label: "running", labelCls: "text-amber-600" },
  failed:    { dotCls: "bg-ip-risk", textCls: "text-ip-risk", label: "failed", labelCls: "text-ip-risk" },
  pending:   { dotCls: "bg-ip-line-strong", textCls: "text-ip-ink-3", label: "pending", labelCls: "text-ip-ink-3" },
};

function TechRow({ name, state }: { name: string; state: StageState }) {
  const ui = STAGE_UI[state];
  return (
    <li className="flex items-center gap-3 px-3 py-2">
      <span className="grid h-5 w-5 shrink-0 place-items-center">
        {state === "completed" ? (
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-ip-recovery" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
        ) : state === "failed" ? (
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-ip-risk" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
        ) : state === "running" ? (
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-70" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-400" />
          </span>
        ) : (
          <span className={`h-2 w-2 rounded-full ${ui.dotCls}`} />
        )}
      </span>
      <span className={`flex-1 text-[13px] ${state === "pending" ? "font-medium" : "font-semibold"} ${ui.textCls}`}>{name}</span>
      <span className={`text-[11px] font-semibold tabular-nums ${ui.labelCls}`}>{ui.label}</span>
    </li>
  );
}

/* ---------------- right rail: project list / launcher ---------------- */
function ProjectRail({
  rows, selectedId, runningId, livePct, onSelect, onRun,
}: {
  rows: ProjectDashboard[];
  selectedId: string | null;
  runningId: string | null;
  livePct: number | null;
  onSelect: (id: string) => void;
  onRun: (id: string) => void;
}) {
  return (
    <Card className="h-fit overflow-hidden">
      <div className="border-b border-ip-line px-4 py-3">
        <div className="ip-label">Projects</div>
      </div>
      <ul className="divide-y divide-ip-line">
        {rows.map((d) => {
          const active = d.project.id === selectedId;
          const status = d.latest_job?.status ?? null;
          const isLive = status === "queued" || status === "running";
          const dot =
            isLive ? "bg-ip-navy" : status === "succeeded" || status === "completed" ? "bg-ip-recovery"
            : status === "failed" ? "bg-ip-risk" : "bg-ip-line-strong";
          return (
            <li key={d.project.id}>
              <button
                onClick={() => onSelect(d.project.id)}
                className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${active ? "bg-ip-navy/[0.05]" : "hover:bg-ip-card-2"}`}
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot} ${isLive ? "animate-pulse" : ""}`} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ip-ink">{d.project.name}</span>
                  <span className="mt-0.5 flex items-center gap-2 text-[11px] text-ip-ink-3">
                    <span className="tabular-nums">{d.document_count} docs</span>
                    <span aria-hidden>·</span>
                    <span>
                      {active && isLive && livePct != null ? `${livePct}%` : d.latest_job ? d.latest_job.status : "never run"}
                    </span>
                  </span>
                </span>
                {d.latest_job?.recoverable_total != null && (
                  <span className="shrink-0 text-[12px] font-bold tabular-nums text-ip-recovery">{aud(d.latest_job.recoverable_total)}</span>
                )}
              </button>
              {active && (
                <div className="px-4 pb-3">
                  <button
                    onClick={() => onRun(d.project.id)}
                    disabled={runningId === d.project.id}
                    className="btn-navy w-full text-xs"
                  >
                    {runningId === d.project.id ? "Queuing…" : "Run analysis"}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/* small inline spinner (respects reduced-motion via the global reset) */
function Spin() {
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 animate-spin" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.2" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
