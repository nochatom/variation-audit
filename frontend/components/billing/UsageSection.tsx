"use client";

import { Card } from "@/components/ui";
import { Usage } from "@/lib/billing/api";

function Meter({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const pct = limit == null ? 100 : Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  const near = limit != null && used / Math.max(limit, 1) >= 0.9;
  const valueLabel = `${label}: ${used.toLocaleString()}${limit == null ? " (unlimited)" : ` of ${limit.toLocaleString()}`}`;

  // Rendered as SVG rather than a div with an inline `width` style: this
  // app's CSP is `style-src 'self'` with no unsafe-inline/hashes (see
  // next.config.js — deliberate, and verified no inline <style> is emitted
  // anywhere else), so a dynamically computed style="width:N%" is silently
  // dropped by the browser. SVG width/x are presentation attributes, not
  // covered by style-src, so the fill actually renders.
  return (
    <div>
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="font-semibold text-ip-ink">{label}</span>
        <span className="tabular-nums text-ip-ink-2">
          {used.toLocaleString()} {limit == null ? "" : `/ ${limit.toLocaleString()}`}
          {limit == null && <span className="text-ip-ink-3"> · unlimited</span>}
        </span>
      </div>
      <svg
        viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label={valueLabel}
        className="mt-1.5 h-2 w-full overflow-hidden rounded-full"
      >
        <rect x="0" y="0" width="100" height="8" rx="4" className="fill-ip-line-strong" />
        <rect
          x="0" y="0" width={pct} height="8" rx="4"
          className={limit == null ? "fill-ip-navy/50" : near ? "fill-ip-risk" : "fill-ip-navy"}
        />
      </svg>
    </div>
  );
}

export function UsageSection({ usage }: { usage: Usage }) {
  const periodLabel = new Date(usage.period_start).toLocaleDateString("en-AU", { month: "long", year: "numeric" });
  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-bold text-ip-ink">Usage this month</h2>
        <span className="text-[12px] text-ip-ink-3">{periodLabel}</span>
      </div>
      <div className="mt-4 space-y-4">
        <Meter label="Active projects" used={usage.projects_active} limit={usage.projects_limit} />
        <Meter label="Documents processed" used={usage.documents_processed} limit={usage.documents_limit} />
        <Meter label="Analysis runs" used={usage.analysis_runs} limit={usage.analysis_runs_limit} />
      </div>
      {usage.seats_limit != null && (
        <p className="mt-4 text-[12px] text-ip-ink-3">Seat limit for the {usage.plan} plan: {usage.seats_limit}.</p>
      )}
    </Card>
  );
}
