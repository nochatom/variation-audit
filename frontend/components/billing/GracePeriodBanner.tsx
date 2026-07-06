"use client";

import { Subscription } from "@/lib/billing/api";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Shown while a recurring payment has failed but the org is still inside its
 * grace period (subscription.status === "past_due") — access is unaffected
 * until grace_period_expires_at passes, so this is a warning, not a block.
 * A "suspended" subscription (grace period already expired) gets a harder
 * banner since plan-limited actions are now actually rejected server-side.
 */
export function GracePeriodBanner({ subscription, onManage }: { subscription: Subscription; onManage: () => void }) {
  if (subscription.status === "past_due" && subscription.grace_period_expires_at) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-ip-orange/30 bg-ip-orange/12 px-4 py-3">
        <p className="text-[13px] text-ip-ink-2">
          <strong className="text-ip-ink">Your last payment failed.</strong> Update your payment method by{" "}
          {fmtDate(subscription.grace_period_expires_at)} to avoid your account being suspended.
        </p>
        <button className="btn-navy shrink-0 text-xs" onClick={onManage}>Update payment method</button>
      </div>
    );
  }

  if (subscription.status === "suspended") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-ip-risk/30 bg-ip-risk-bg px-4 py-3">
        <p className="text-[13px] text-ip-risk">
          <strong>Account suspended</strong> after a failed payment — document uploads and analysis are blocked
          until your payment method is updated.
        </p>
        <button className="btn-navy shrink-0 text-xs" onClick={onManage}>Update payment method</button>
      </div>
    );
  }

  return null;
}
