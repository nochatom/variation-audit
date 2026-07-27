"use client";

import { Usage } from "@/lib/billing/api";

function pct(used: number, limit: number): number {
  return Math.min(100, Math.max(0, Math.round((used / Math.max(limit, 1)) * 100)));
}

/** Claude-style usage indicator for the monthly analysis quota: plan name,
 * "used / limit" and "remaining" counts, a percent-used figure, and a
 * progress bar — not just a bare remaining-count number. Renders nothing for
 * an unlimited plan (analysis_runs_limit === null), since there's no quota
 * to visualize.
 *
 * The backend is the sole source of truth (usage.analysis_runs comes from
 * the immutable analysis_usage_events ledger, see app/models.py) — this
 * component only ever reflects whatever `usage` prop it's given. Callers are
 * responsible for refetching `usage` (billingApi.getUsage) after any action
 * that can change it, e.g. right after an analysis job completes. */
export function FreeUsageMeter({ usage, onUpgrade }: { usage: Usage; onUpgrade?: () => void }) {
  const limit = usage.analysis_runs_limit;
  if (limit == null) return null;

  const used = usage.analysis_runs;
  const remaining = Math.max(0, limit - used);
  const percent = pct(used, limit);
  const atCap = used >= limit;
  const near = !atCap && percent >= 80;
  const planLabel = `${usage.plan.charAt(0).toUpperCase()}${usage.plan.slice(1)} Plan`;
  const barLabel = `${percent}% of monthly analysis quota used — ${used} of ${limit} analyses`;

  return (
    <div className="rounded-lg border border-ip-line bg-ip-card p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] font-bold text-ip-ink">{planLabel}</span>
        <span className="tabular-nums text-[12px] font-semibold text-ip-ink-2">{percent}% used</span>
      </div>
      <p className="mt-1.5 text-[13px] text-ip-ink">
        <span className="font-semibold tabular-nums">{used} / {limit}</span>{" "}
        <span className="text-ip-ink-2">analyses used</span>
      </p>
      <p className="text-[12px] text-ip-ink-3">
        {remaining} {remaining === 1 ? "analysis" : "analyses"} remaining
      </p>

      {/* SVG, not a div with inline width: this app's CSP is style-src
          'self' with no unsafe-inline (see next.config.js) — a dynamic
          style="width:N%" would be silently dropped. SVG width/x are
          presentation attributes, not covered by style-src. */}
      <svg
        viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label={barLabel}
        className="mt-2.5 h-2 w-full overflow-hidden rounded-full"
      >
        <rect x="0" y="0" width="100" height="8" rx="4" className="fill-ip-line-strong" />
        <rect
          x="0" y="0" width={percent} height="8" rx="4"
          className={atCap ? "fill-ip-risk" : near ? "fill-ip-orange" : "fill-ip-navy"}
        />
      </svg>

      {/* Hitting the cap is the highest-intent moment there is — it gets an
          action, not a sentence telling the user to go find one. */}
      {(atCap || near) && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <p className={`flex-1 text-[12px] font-medium ${atCap ? "text-ip-risk" : "text-ip-orange-2"}`}>
            {atCap
              ? `You've used all ${limit} analyses this month.`
              : `${remaining} of ${limit} analyses left this month.`}
          </p>
          {onUpgrade && (
            <button onClick={onUpgrade} className={atCap ? "btn-orange" : "btn-ghost"}>
              Upgrade plan
            </button>
          )}
        </div>
      )}
    </div>
  );
}
