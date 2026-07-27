"use client";

import { Usage } from "@/lib/billing/api";
import { bindingLimit, isMonthly, LimitRow, resetsAt } from "@/lib/billing/limits";

/** What the user actually came here to resolve.
 *
 * Nobody opens billing to be told which plan they are on — they open it
 * because something stopped working. This states the blocked thing in one
 * sentence and puts the action next to it. Renders nothing when no limit is
 * binding, so a healthy org sees no banner at all rather than a reassuring
 * box that costs a screenful. */
function copy(row: LimitRow, usage: Usage): { headline: string; detail: string } {
  const reset = resetsAt(usage).toLocaleDateString("en-AU", { day: "numeric", month: "long" });
  const count = `${row.used.toLocaleString()} of ${row.limit?.toLocaleString()}`;

  if (row.key === "analysis_runs") {
    return {
      headline: row.state === "over" ? "You're out of analysis runs." : "You've used your last analysis run.",
      detail: `${count} used this month. New analyses are blocked until ${reset}, or immediately if you upgrade.`,
    };
  }
  if (row.key === "documents") {
    return {
      headline: "You've reached your document limit.",
      detail: `${count} processed this month. Uploads are blocked until ${reset}, or immediately if you upgrade.`,
    };
  }
  return {
    headline: "You've reached your project limit.",
    detail: `${count} active. Archive a project to free a slot, or upgrade to add more.`,
  };
}

export function BindingConstraint({
  usage,
  onUpgrade,
}: {
  usage: Usage;
  onUpgrade?: () => void;
}) {
  const row = bindingLimit(usage);
  if (!row) return null;

  const { headline, detail } = copy(row, usage);
  const over = row.state === "over";

  return (
    // Severity is carried by the rail, the heading colour AND the wording, not
    // by colour alone — `--ip-orange` is a non-text accent per globals.css, so
    // it only ever fills the rail here, never the type.
    <section
      aria-labelledby="binding-headline"
      className={`rounded-lg border border-ip-line bg-ip-card p-5 border-l-[3px] ${
        over ? "border-l-ip-risk" : "border-l-ip-orange"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2
            id="binding-headline"
            className={`text-lg font-bold tracking-[-0.015em] ${over ? "text-ip-risk" : "text-ip-ink"}`}
          >
            {headline}
          </h2>
          <p className="mt-1 max-w-[54ch] text-[13px] text-ip-ink-2">{detail}</p>
        </div>
        {onUpgrade && (
          <button className="btn-navy" onClick={onUpgrade}>
            Upgrade plan
          </button>
        )}
      </div>
      {!isMonthly(row.key) && (
        <p className="mt-3 text-[12px] text-ip-ink-3">
          Project slots do not reset monthly — archiving is the only way to free one on your
          current plan.
        </p>
      )}
    </section>
  );
}
