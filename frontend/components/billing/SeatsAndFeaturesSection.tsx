"use client";

import { Card, Chip } from "@/components/ui";
import { Features, Seats } from "@/lib/billing/api";

const FEATURE_LABEL: Record<keyof Features, string> = {
  audit_log: "Audit log",
  exports: "Data exports",
  sso: "Single sign-on (SSO)",
  priority_support: "Priority support",
  advanced_analytics: "Advanced analytics",
};

export function SeatsAndFeaturesSection({ seats, features }: { seats: Seats; features: Features }) {
  return (
    <Card className="p-5">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <h2 className="text-sm font-bold text-ip-ink">Seats</h2>
          <div className="mt-3 flex items-baseline justify-between text-[13px]">
            <span className="text-ip-ink-2">In use</span>
            <span className="tabular-nums font-semibold text-ip-ink">
              {seats.current_seats}
              {seats.included_seats != null ? ` / ${seats.included_seats}` : ""}
              {seats.included_seats == null && <span className="ml-1 text-ip-ink-3">· unlimited</span>}
            </span>
          </div>
          {seats.billable_seats > 0 && (
            <p className="mt-2 text-[12px] text-ip-ink-3">
              {seats.billable_seats} seat{seats.billable_seats === 1 ? "" : "s"} over your included allowance —
              billed as additional seats on your subscription.
            </p>
          )}
        </div>
        <div>
          <h2 className="text-sm font-bold text-ip-ink">Plan features</h2>
          <ul className="mt-3 space-y-1.5">
            {(Object.keys(FEATURE_LABEL) as (keyof Features)[]).map((key) => (
              <li key={key} className="flex items-center justify-between text-[13px]">
                <span className="text-ip-ink-2">{FEATURE_LABEL[key]}</span>
                {features[key] ? <Chip tone="recovery">included</Chip> : <Chip>not included</Chip>}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}
