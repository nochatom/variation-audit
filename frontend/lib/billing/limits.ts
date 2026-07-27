import { Usage } from "./api";

/** One plan limit, resolved against current usage.
 *
 * Both the binding-constraint banner and the usage meters read from this, so
 * they cannot disagree about which limit is under the most pressure — the old
 * layout hardcoded that judgement into markup order and only ever dressed up
 * analysis runs, which is wrong for any org whose projects or documents bind
 * first. */
export type LimitState = "unlimited" | "ok" | "near" | "at" | "over";

export type LimitRow = {
  key: "analysis_runs" | "projects" | "documents";
  label: string;
  used: number;
  limit: number | null;
  /** used / limit. -1 for unlimited, so it always sorts last. */
  ratio: number;
  state: LimitState;
  /** null when unlimited. Floored at 0 — never render a negative remainder. */
  remaining: number | null;
};

const NEAR_THRESHOLD = 0.8;

function resolve(
  key: LimitRow["key"], label: string, used: number, limit: number | null,
): LimitRow {
  if (limit == null) {
    return { key, label, used, limit, ratio: -1, state: "unlimited", remaining: null };
  }
  // A limit of 0 would divide by zero; treat any usage against it as over.
  const ratio = limit === 0 ? (used > 0 ? Infinity : 0) : used / limit;
  const state: LimitState =
    used > limit ? "over" : used === limit ? "at" : ratio >= NEAR_THRESHOLD ? "near" : "ok";
  return { key, label, used, limit, ratio, state, remaining: Math.max(0, limit - used) };
}

const RANK: Record<LimitState, number> = { over: 0, at: 1, near: 2, ok: 3, unlimited: 4 };

/** Every limit, sorted by how close it is to blocking the user. */
export function limitRows(usage: Usage): LimitRow[] {
  return [
    resolve("analysis_runs", "Analysis runs", usage.analysis_runs, usage.analysis_runs_limit),
    resolve("projects", "Active projects", usage.projects_active, usage.projects_limit),
    resolve("documents", "Documents processed", usage.documents_processed, usage.documents_limit),
  ].sort((a, b) => RANK[a.state] - RANK[b.state] || b.ratio - a.ratio);
}

/** The limit worth interrupting the user about, or null when nothing binds.
 *
 * "near" deliberately does NOT qualify: warning someone at 80% every time they
 * open billing trains them to ignore the banner for the case that matters. */
export function bindingLimit(usage: Usage): LimitRow | null {
  const top = limitRows(usage)[0];
  return top && (top.state === "over" || top.state === "at") ? top : null;
}

/** First day of the month after the current usage period — when monthly
 * counters reset. Month-based limits reset; project count does not. */
export function resetsAt(usage: Usage): Date {
  const start = new Date(usage.period_start);
  return new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
}

export function isMonthly(key: LimitRow["key"]): boolean {
  return key === "analysis_runs" || key === "documents";
}
