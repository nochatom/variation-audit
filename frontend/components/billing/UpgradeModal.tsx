"use client";

import { useState } from "react";
import { Modal } from "./Modal";
import { BillingInterval, PlanTier, Subscription } from "@/lib/billing/api";

// Mirrors backend/app/services/billing.py:PLAN_LIMITS + the published AUD
// pricing (see frontend/app/pricing/page.tsx for the full public page).
const PLANS: {
  tier: PlanTier; label: string; monthly: number | null; annual: number | null;
  projects: string; docs: string; runs: string; seats: string; storage: string;
}[] = [
  { tier: "free", label: "Free", monthly: 0, annual: 0,
    projects: "1 project", docs: "20 documents / month", runs: "5 AI analyses / month",
    seats: "Up to 3 seats", storage: "500 MB storage" },
  { tier: "pro", label: "Pro", monthly: 149, annual: 1490,
    projects: "25 projects", docs: "500 documents / month", runs: "100 AI analyses / month",
    seats: "15 included seats", storage: "5 GB storage" },
  { tier: "enterprise", label: "Enterprise", monthly: null, annual: null,
    projects: "Unlimited projects", docs: "Unlimited documents", runs: "Unlimited AI analyses",
    seats: "Unlimited seats", storage: "Unlimited storage" },
];

export function UpgradeModal({
  subscription,
  onClose,
  onCheckout,
  onDowngrade,
}: {
  subscription: Subscription;
  onClose: () => void;
  onCheckout: (plan: "pro" | "enterprise", billingInterval: BillingInterval) => Promise<void>;
  onDowngrade: () => void;
}) {
  const [busyPlan, setBusyPlan] = useState<PlanTier | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [interval, setInterval] = useState<BillingInterval>("monthly");

  async function upgrade(plan: "pro" | "enterprise") {
    setBusyPlan(plan);
    setNotice(null);
    try {
      await onCheckout(plan, interval);
    } catch (e: any) {
      // The backend's error message is already written to be shown as-is
      // (covers "not configured yet — contact sales" and "already on a
      // paid plan — use Manage billing" without needing to special-case
      // status codes here).
      setNotice(e.message);
    } finally {
      setBusyPlan(null);
    }
  }

  return (
    <Modal title="Change plan" onClose={onClose}>
      <div
        role="group"
        aria-label="Billing interval selection"
        className="flex items-center justify-center gap-2 rounded-pill bg-ip-card-2 p-1 text-[12px] font-semibold"
      >
        <button
          aria-pressed={interval === "monthly"}
          className={`rounded-pill px-3 py-1 ${interval === "monthly" ? "bg-ip-navy text-white" : "text-ip-ink-2"}`}
          onClick={() => setInterval("monthly")}
        >
          Monthly
        </button>
        <button
          aria-pressed={interval === "annual"}
          className={`rounded-pill px-3 py-1 ${interval === "annual" ? "bg-ip-navy text-white" : "text-ip-ink-2"}`}
          onClick={() => setInterval("annual")}
        >
          Annual <span className="text-ip-recovery">· 2 months free</span>
        </button>
      </div>

      {notice && <p className="mt-3 rounded-md border border-ip-orange/30 bg-ip-orange/12 px-3 py-2 text-[13px] text-ip-ink-2">{notice}</p>}

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {PLANS.map((p) => {
          const isCurrent = subscription.plan === p.tier;
          const isUpgrade = p.tier !== "free" && !isCurrent;
          const isDowngradeToFree = p.tier === "free" && subscription.plan !== "free";
          const price = interval === "monthly" ? p.monthly : p.annual;
          return (
            <div key={p.tier} className={`rounded-md border p-4 ${isCurrent ? "border-ip-navy" : "border-ip-line"}`}>
              <div className="text-sm font-bold text-ip-ink">{p.label}</div>
              <div className="mt-1 text-[13px] font-semibold tabular-nums text-ip-ink">
                {p.tier === "enterprise" ? "Contact Sales" : price === 0 ? (
                  <>A$0 <span className="font-normal text-ip-ink-3">Forever</span></>
                ) : (
                  <>AUD {price!.toLocaleString()} <span className="font-normal text-ip-ink-3">/ {interval === "monthly" ? "mo" : "yr"}</span></>
                )}
              </div>
              <ul className="mt-2 space-y-1 text-[12px] text-ip-ink-2">
                <li>{p.projects}</li>
                <li>{p.docs}</li>
                <li>{p.runs}</li>
                <li>{p.seats}</li>
                <li>{p.storage}</li>
              </ul>
              <div className="mt-3">
                {isCurrent && (
                  <span className="inline-block rounded-pill bg-ip-navy/10 px-2.5 py-1 text-[11px] font-semibold text-ip-navy">Current plan</span>
                )}
                {isUpgrade && p.tier === "enterprise" && (
                  <a href="mailto:hello@variationiq.com" className="btn-navy block w-full text-center text-xs">Contact Sales</a>
                )}
                {isUpgrade && p.tier !== "enterprise" && (
                  <button
                    className="btn-navy w-full text-xs"
                    disabled={busyPlan !== null}
                    onClick={() => upgrade(p.tier as "pro" | "enterprise")}
                  >
                    {busyPlan === p.tier ? "Starting checkout…" : `Upgrade to ${p.label}`}
                  </button>
                )}
                {isDowngradeToFree && (
                  <button className="btn-ghost w-full text-xs" onClick={onDowngrade} disabled={busyPlan !== null}>
                    Downgrade to Free
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
