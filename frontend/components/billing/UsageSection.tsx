"use client";

import { Card } from "@/components/ui";
import { Usage } from "@/lib/billing/api";
import { limitRows, LimitRow } from "@/lib/billing/limits";

/** Fill colour per state. Orange and risk are indicator fills only — the
 * matching text stays ink, since `--ip-orange` fails contrast as type (see the
 * note in globals.css). */
const FILL: Record<LimitRow["state"], string> = {
  over: "fill-ip-risk",
  at: "fill-ip-orange",
  near: "fill-ip-orange",
  ok: "fill-ip-navy",
  unlimited: "fill-ip-navy/50",
};

function tail(row: LimitRow): string {
  switch (row.state) {
    case "unlimited": return "unlimited";
    case "over": return `over by ${(row.used - (row.limit ?? 0)).toLocaleString()}`;
    case "at": return "at limit";
    default: return `${row.remaining?.toLocaleString()} left`;
  }
}

function Meter({ row }: { row: LimitRow }) {
  const pct = row.limit == null ? 100 : Math.min(100, Math.round(row.ratio * 100));
  const valueLabel =
    row.limit == null
      ? `${row.label}: ${row.used.toLocaleString()} (unlimited)`
      : `${row.label}: ${row.used.toLocaleString()} of ${row.limit.toLocaleString()} — ${tail(row)}`;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className={`font-semibold ${row.state === "over" ? "text-ip-risk" : "text-ip-ink"}`}>
          {row.label}
        </span>
        <span className="whitespace-nowrap tabular-nums text-ip-ink-2">
          <span className={row.state === "over" ? "font-bold text-ip-risk" : "font-semibold text-ip-ink"}>
            {row.used.toLocaleString()}
            {row.limit != null && ` / ${row.limit.toLocaleString()}`}
          </span>
          <span className="text-ip-ink-3"> · {tail(row)}</span>
        </span>
      </div>
      {/* SVG rather than a div with an inline `width` style: this app's CSP is
          `style-src 'self'` with no unsafe-inline (see next.config.js), so a
          dynamically computed style="width:N%" is silently dropped. SVG
          width/x are presentation attributes and are not covered by
          style-src, so the fill actually renders. */}
      <svg
        viewBox="0 0 100 8" preserveAspectRatio="none" role="img" aria-label={valueLabel}
        className="mt-1.5 h-2 w-full overflow-hidden rounded-full"
      >
        <rect x="0" y="0" width="100" height="8" rx="4" className="fill-ip-line-strong" />
        <rect x="0" y="0" width={pct} height="8" rx="4" className={FILL[row.state]} />
      </svg>
    </div>
  );
}

export function UsageSection({ usage }: { usage: Usage }) {
  const periodLabel = new Date(usage.period_start).toLocaleDateString("en-AU", {
    month: "long", year: "numeric",
  });
  // Sorted by pressure, so whatever is closest to blocking the user reads
  // first. One flat list inside one card: the old layout nested a
  // `bg-ip-card` block inside this `<Card>`, and --ip-card is 255 255 255, so
  // it was white on white separated only by a hairline.
  const rows = limitRows(usage);

  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-bold text-ip-ink">Usage this month</h2>
        <span className="text-[12px] text-ip-ink-3">{periodLabel}</span>
      </div>
      <div className="mt-4 space-y-4">
        {rows.map((row) => (
          <Meter key={row.key} row={row} />
        ))}
      </div>
      {usage.seats_limit != null && (
        <p className="mt-4 text-[12px] text-ip-ink-3">
          Seat limit for the {usage.plan} plan: {usage.seats_limit}.
        </p>
      )}
    </Card>
  );
}
