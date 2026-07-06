"use client";

import { Card } from "@/components/ui";
import { Subscription } from "@/lib/billing/api";

/**
 * Card capture and display always happens inside Stripe's hosted Checkout /
 * Billing Portal — never on a form this app hosts — so a raw card number
 * never touches our backend. "Manage billing" opens that hosted portal.
 */
export function PaymentMethodSection({ subscription, onManage, busy }: {
  subscription: Subscription;
  onManage: () => void;
  busy?: boolean;
}) {
  return (
    <Card className="p-5">
      <h2 className="text-sm font-bold text-ip-ink">Payment method</h2>
      {subscription.has_payment_method ? (
        <div className="mt-3 flex items-center justify-between rounded-md border border-ip-line px-3 py-2.5">
          <div className="flex items-center gap-2 text-[13px] text-ip-ink-2">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-5 w-5 text-ip-ink-3">
              <rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" />
            </svg>
            Card on file — managed securely by Stripe
          </div>
          <button className="btn-ghost px-2.5 py-1 text-xs" onClick={onManage} disabled={busy}>Manage</button>
        </div>
      ) : (
        <p className="mt-3 text-[13px] text-ip-ink-2">
          No payment method on file. One is added automatically through Stripe&apos;s secure checkout the first
          time you upgrade to a paid plan.
        </p>
      )}
    </Card>
  );
}
