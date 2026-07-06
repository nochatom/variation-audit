"use client";

// Billing service layer — thin wrapper over the shared `request()` client in
// lib/api.ts (same bearer-token attach + refresh-and-retry behaviour), scoped
// to the /orgs/{companyId}/billing/* endpoints. Kept as its own module so the
// billing feature (components/billing/*, lib/billing/hooks.ts) doesn't need
// to reach into the general-purpose api.ts object.

import { request } from "@/lib/api";

export type PlanTier = "free" | "pro" | "enterprise";

export type Subscription = {
  plan: PlanTier;
  status: "active" | "trialing" | "past_due" | "suspended" | "canceled";
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  has_payment_method: boolean;
  // Set only while status is "past_due" — a recurring payment failed and
  // the org is inside its grace period (see backend/app/config.py
  // billing_grace_period_days); access is unaffected until this passes.
  grace_period_expires_at: string | null;
};

export type Seats = {
  current_seats: number;
  included_seats: number | null;
  billable_seats: number;
  additional_seats: number;
};

export type Features = {
  audit_log: boolean;
  exports: boolean;
  sso: boolean;
  priority_support: boolean;
  advanced_analytics: boolean;
};

export type BillingAuditEntry = {
  id: string;
  actor_user_id: string | null;
  action: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type Usage = {
  plan: PlanTier;
  period_start: string;
  projects_active: number;
  projects_limit: number | null;
  documents_processed: number;
  documents_limit: number | null;
  analysis_runs: number;
  analysis_runs_limit: number | null;
  seats_limit: number | null;
};

export type BillingInterval = "monthly" | "annual";

export type Invoice = {
  id: string;
  plan: PlanTier;
  amount: string;
  currency: string;
  status: "paid" | "open" | "void";
  period_start: string;
  period_end: string;
  hosted_invoice_url: string | null;
};

export const billingApi = {
  getSubscription: (companyId: string) =>
    request<Subscription>(`/orgs/${companyId}/billing/subscription`),
  getUsage: (companyId: string) => request<Usage>(`/orgs/${companyId}/billing/usage`),
  listInvoices: (companyId: string) => request<Invoice[]>(`/orgs/${companyId}/billing/invoices`),

  /** Returns a Stripe Checkout URL, or throws (409) if the plan/interval has
   * no live Stripe Price configured yet — callers should treat that as "not
   * self-serve yet, contact sales" rather than a hard error. */
  startCheckout: (companyId: string, plan: "pro" | "enterprise", billingInterval: BillingInterval = "monthly") =>
    request<{ url: string }>(`/orgs/${companyId}/billing/checkout`, {
      method: "POST",
      body: JSON.stringify({ plan, billing_interval: billingInterval }),
    }),

  /** Returns a Stripe Billing Portal URL for managing payment method,
   * invoices, and plan — throws (409) if no billing account exists yet
   * (i.e. still on Free, never checked out). */
  startPortal: (companyId: string) =>
    request<{ url: string }>(`/orgs/${companyId}/billing/portal`, { method: "POST" }),

  cancelSubscription: (companyId: string) =>
    request<Subscription>(`/orgs/${companyId}/billing/cancel`, { method: "POST" }),

  /** Undo a pending cancellation — throws (409) if the subscription isn't
   * currently set to cancel at period end. */
  resumeSubscription: (companyId: string) =>
    request<Subscription>(`/orgs/${companyId}/billing/resume`, { method: "POST" }),

  getSeats: (companyId: string) => request<Seats>(`/orgs/${companyId}/billing/seats`),
  getFeatures: (companyId: string) => request<Features>(`/orgs/${companyId}/billing/features`),
  getBillingAudit: (companyId: string) =>
    request<BillingAuditEntry[]>(`/orgs/${companyId}/billing/audit`),
};
