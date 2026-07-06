"use client";

import { Card, Chip } from "@/components/ui";
import { Subscription } from "@/lib/billing/api";

const PLAN_LABEL: Record<string, string> = { free: "Free", pro: "Pro", enterprise: "Enterprise" };
const STATUS_TONE: Record<string, string> = {
  active: "recovery", trialing: "navy", past_due: "risk", suspended: "risk", canceled: "neutral",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

export function PlanCard({
  subscription,
  onUpgrade,
  onManage,
  onCancel,
  onResume,
  busy,
}: {
  subscription: Subscription;
  onUpgrade: () => void;
  onManage: () => void;
  onCancel: () => void;
  onResume: () => void;
  busy?: boolean;
}) {
  const isPaid = subscription.plan !== "free";

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="ip-label">Current plan</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-xl font-bold text-ip-ink">{PLAN_LABEL[subscription.plan] ?? subscription.plan}</span>
            <Chip tone={STATUS_TONE[subscription.status] ?? "neutral"}>{subscription.status.replace("_", " ")}</Chip>
            {subscription.cancel_at_period_end && <Chip tone="risk">cancels at period end</Chip>}
          </div>
          <div className="mt-2 text-[13px] text-ip-ink-2">
            {isPaid
              ? `Renews ${fmtDate(subscription.current_period_end)}`
              : "No renewal date — the Free plan does not expire."}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {isPaid && subscription.has_payment_method && (
            <button className="btn-ghost" onClick={onManage} disabled={busy}>Manage billing</button>
          )}
          {subscription.cancel_at_period_end ? (
            <button className="btn-navy" onClick={onResume} disabled={busy}>Resume subscription</button>
          ) : (
            <button className="btn-navy" onClick={onUpgrade} disabled={busy}>
              {isPaid ? "Change plan" : "Upgrade plan"}
            </button>
          )}
          {isPaid && !subscription.cancel_at_period_end && (
            <button
              onClick={onCancel}
              disabled={busy}
              className="rounded-md bg-ip-risk/10 px-3 py-2 text-sm font-semibold text-ip-risk hover:bg-ip-risk/20"
            >
              Cancel subscription
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}
