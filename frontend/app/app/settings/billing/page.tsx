"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useApp } from "@/lib/app-context";
import { billingApi, BillingInterval } from "@/lib/billing/api";
import { useFeatures, useInvoices, useSeats, useSubscription, useUsage } from "@/lib/billing/hooks";
import { PageHeader, ErrorNote, InfoNote, Spinner, EmptyState } from "@/components/ui";
import { PlanCard } from "@/components/billing/PlanCard";
import { UsageSection } from "@/components/billing/UsageSection";
import { PaymentMethodSection } from "@/components/billing/PaymentMethodSection";
import { InvoicesSection } from "@/components/billing/InvoicesSection";
import { UpgradeModal } from "@/components/billing/UpgradeModal";
import { CancelModal } from "@/components/billing/CancelModal";
import { GracePeriodBanner } from "@/components/billing/GracePeriodBanner";
import { SeatsAndFeaturesSection } from "@/components/billing/SeatsAndFeaturesSection";

export default function BillingPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <BillingPageInner />
    </Suspense>
  );
}

function BillingPageInner() {
  const { companyId, isAdmin } = useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sub = useSubscription(companyId);
  const usage = useUsage(companyId);
  const invoices = useInvoices(companyId);
  const seats = useSeats(companyId);
  const features = useFeatures(companyId);

  const [showUpgrade, setShowUpgrade] = useState(false);
  const [showCancel, setShowCancel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Stripe redirects here with ?checkout=success|cancelled after Checkout.
  // The webhook that actually updates the subscription can land a moment
  // after this redirect, so this is a status message, not a guarantee the
  // new plan is visible yet — strip the param from the URL once shown so a
  // page refresh doesn't keep re-showing it.
  const checkoutResult = searchParams.get("checkout");
  useEffect(() => {
    if (!checkoutResult) return;
    if (checkoutResult === "success") sub.reload();
    const url = new URL(window.location.href);
    url.searchParams.delete("checkout");
    router.replace(url.pathname + url.search);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkoutResult]);

  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="Billing & subscription" description="Manage your organization's plan and payment details." />
        <EmptyState title="Admin access required" body="Only organization admins can view or manage billing." />
      </div>
    );
  }

  async function manageBilling() {
    if (!companyId) return;
    setBusy(true);
    setActionError(null);
    try {
      const { url } = await billingApi.startPortal(companyId);
      window.location.href = url;
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function checkout(plan: "pro" | "enterprise", billingInterval: BillingInterval) {
    if (!companyId) return;
    const { url } = await billingApi.startCheckout(companyId, plan, billingInterval);
    window.location.href = url;
  }

  async function cancelSubscription() {
    if (!companyId) return;
    await billingApi.cancelSubscription(companyId);
    await sub.reload();
  }

  async function downgradeToFree() {
    setShowUpgrade(false);
    setShowCancel(true);
  }

  async function resumeSubscription() {
    if (!companyId) return;
    setBusy(true);
    setActionError(null);
    try {
      await billingApi.resumeSubscription(companyId);
      await sub.reload();
    } catch (e: any) {
      setActionError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Link href="/app/settings" className="mb-3 inline-flex items-center gap-1 text-[13px] font-medium text-ip-ink-2 hover:text-ip-ink">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3.5 w-3.5"><path d="M15 18l-6-6 6-6" /></svg>
        Settings
      </Link>
      <PageHeader title="Billing & subscription" description="Manage your organization's plan, usage, and payment details." />
      {checkoutResult === "success" && (
        <div className="mb-4">
          <InfoNote>Payment successful — your plan will update within a few seconds.</InfoNote>
        </div>
      )}
      {checkoutResult === "cancelled" && (
        <div className="mb-4">
          <InfoNote>Checkout was cancelled — no changes were made to your plan.</InfoNote>
        </div>
      )}
      {actionError && <ErrorNote message={actionError} />}
      {sub.error && <ErrorNote message={sub.error} />}

      {sub.loading && !sub.data && <Spinner />}
      {sub.data && (
        <div className="space-y-6">
          <GracePeriodBanner subscription={sub.data} onManage={manageBilling} />

          <PlanCard
            subscription={sub.data}
            busy={busy}
            onUpgrade={() => setShowUpgrade(true)}
            onManage={manageBilling}
            onCancel={() => setShowCancel(true)}
            onResume={resumeSubscription}
          />

          {usage.data && <UsageSection usage={usage.data} />}

          {seats.data && features.data && (
            <SeatsAndFeaturesSection seats={seats.data} features={features.data} />
          )}

          <PaymentMethodSection subscription={sub.data} onManage={manageBilling} busy={busy} />

          {invoices.error && <ErrorNote message={invoices.error} />}
          {invoices.loading && !invoices.data && <Spinner />}
          {invoices.data && <InvoicesSection invoices={invoices.data} />}
        </div>
      )}

      {showUpgrade && sub.data && (
        <UpgradeModal
          subscription={sub.data}
          onClose={() => setShowUpgrade(false)}
          onCheckout={checkout}
          onDowngrade={downgradeToFree}
        />
      )}
      {showCancel && (
        <CancelModal onClose={() => setShowCancel(false)} onConfirm={cancelSubscription} />
      )}
    </div>
  );
}
