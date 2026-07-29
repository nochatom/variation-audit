import { test as base, expect, Page } from "@playwright/test";

/**
 * Shared test fixtures.
 *
 * `mockApi` intercepts every backend call the frontend makes (default base
 * http://localhost:8000) and returns deterministic fixtures — so the app
 * renders real authenticated UI with zero backend/engine/Postgres running.
 * This is intentional: these tests verify the frontend, deterministically,
 * on every PR. Backend behaviour is covered by the pytest suite.
 *
 * `authedPage` additionally seeds the localStorage tokens the app checks for
 * before mounting the authenticated shell (see lib/api.ts / app-context.tsx),
 * so `/app/*` routes render instead of bouncing to /login.
 */

const COMPANY_ID = "11111111-1111-4111-8111-111111111111";
const USER_ID = "22222222-2222-4222-8222-222222222222";

const ME = {
  user_id: USER_ID,
  email: "demo@variationiq.com",
  full_name: "Demo Admin",
  organizations: [{ id: COMPANY_ID, name: "Demo Construction Co", role: "admin" }],
};

// Shape must match lib/api.ts OrgDashboard exactly.
const COUNTS = { pending: 4, confirmed: 6, rejected: 2, total: 12 };
const ORG_DASHBOARD = {
  totals: { projects: 2, pending: 4, confirmed: 6, recoverable_confirmed: 284500, currency: "AUD" },
  projects: [
    {
      id: "33333333-3333-4333-8333-333333333333",
      name: "Sydney Metro — Package 4",
      status: "in_progress",
      has_contract: true,
      counts: COUNTS,
      recoverable_confirmed: 284500,
      time_bar_at_risk: 3,
    },
  ],
};

// Shapes must match lib/billing/api.ts exactly — a missing/renamed field
// makes a billing sub-component throw into the error boundary.
const SUBSCRIPTION = {
  plan: "free",
  status: "active",
  current_period_end: null,
  cancel_at_period_end: false,
  has_payment_method: false,
  grace_period_expires_at: null,
};
const USAGE = {
  plan: "free",
  period_start: "2026-07-01T00:00:00Z",
  projects_active: 1, projects_limit: 1,
  documents_processed: 3, documents_limit: 20,
  analysis_runs: 0, analysis_runs_limit: 5,
  seats_limit: 3,
};
const SEATS = { current_seats: 1, included_seats: 3, billable_seats: 1, additional_seats: 0 };
const FEATURES = { audit_log: false, exports: false, sso: false, priority_support: false, advanced_analytics: false };

// The frontend calls the API cross-origin (localhost:8000 from the :3100
// test server), so the browser sends a CORS preflight and requires
// Access-Control-* headers on the real response — without them fetch()
// rejects and the app bounces to /login. Every mock therefore carries CORS
// headers, and OPTIONS preflights are answered 204.
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "*",
};

// Backend origin the frontend calls (NEXT_PUBLIC_API_BASE_URL default).
// Every mock is scoped under this so no glob can shadow a frontend route.
const B = "**localhost:8000";

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", headers: CORS, body: JSON.stringify(body) };
}

/** Register all backend route mocks on a page (or its context). */
export async function mockApi(page: Page) {
  // Catch-all registered FIRST so it has LOWEST priority — Playwright
  // evaluates routes in reverse-registration order, so the specific routes
  // below (registered later) win for their URLs. This handles CORS
  // preflights and returns an empty CORS'd 200 for any endpoint not
  // explicitly mocked, instead of a hung request to a non-running backend.
  await page.route("**/localhost:8000/**", (route, request) =>
    route.fulfill(request.method() === "OPTIONS" ? { status: 204, headers: CORS, body: "" } : json({})),
  );
  // Every specific route is HOST-SCOPED to the backend origin (B) so a broad
  // glob like "/projects" can never intercept the frontend's own
  // "/app/projects" page navigation on :3100 (which would replace the page
  // with raw JSON). Trailing "*" tolerates query strings.
  await page.route(`${B}/auth/me`, (r) => r.fulfill(json(ME)));
  await page.route(`${B}/auth/login`, (r) =>
    r.fulfill(json({ access_token: "test-access", refresh_token: "test-refresh", user_id: USER_ID, email: ME.email, organizations: ME.organizations })),
  );
  await page.route(`${B}/auth/refresh`, (r) =>
    r.fulfill(json({ access_token: "test-access", refresh_token: "test-refresh" })),
  );
  await page.route(`${B}/auth/logout*`, (r) => r.fulfill(json({}, 204)));
  await page.route(`${B}/notifications/unread-count`, (r) => r.fulfill(json({ count: 0 })));

  await page.route(`${B}/dashboard?*`, (r) => r.fulfill(json(ORG_DASHBOARD)));
  await page.route(`${B}/projects?*`, (r) => r.fulfill(json(ORG_DASHBOARD.projects)));
  // Per-project dashboard (doc count on the Documents page).
  await page.route(`${B}/projects/*/dashboard`, (r) =>
    r.fulfill(json({
      project: { id: ORG_DASHBOARD.projects[0].id, name: ORG_DASHBOARD.projects[0].name, state: "NSW", status: "in_progress", has_contract: true },
      counts: COUNTS,
      recoverable_confirmed: 284500,
      time_bar_at_risk: 3,
      document_count: 3,
      latest_job: { id: "job-1", status: "succeeded", recoverable_total: 284500 },
    })),
  );

  // Project creation — echo a created project.
  await page.route(`${B}/projects`, async (r) => {
    if (r.request().method() === "POST") {
      const body = JSON.parse(r.request().postData() || "{}");
      return r.fulfill(
        json({
          id: "44444444-4444-4444-8444-444444444444",
          company_id: COMPANY_ID,
          name: body.name ?? "New project",
          state: body.state ?? null,
          status: "in_progress",
          has_contract: false,
          archived_at: null,
        }, 201),
      );
    }
    return r.fulfill(json(ORG_DASHBOARD.projects));
  });

  // Contract/document upload — accept and report has_contract.
  await page.route(`${B}/projects/*/contract*`, (r) =>
    r.fulfill(json({
      id: "44444444-4444-4444-8444-444444444444",
      company_id: COMPANY_ID, name: "New project", state: "NSW",
      status: "in_progress", has_contract: true, archived_at: null,
    })),
  );

  // Billing.
  await page.route(`${B}/**/billing/subscription`, (r) => r.fulfill(json(SUBSCRIPTION)));
  await page.route(`${B}/**/billing/usage`, (r) => r.fulfill(json(USAGE)));
  await page.route(`${B}/**/billing/seats`, (r) => r.fulfill(json(SEATS)));
  await page.route(`${B}/**/billing/features`, (r) => r.fulfill(json(FEATURES)));
  await page.route(`${B}/**/billing/invoices`, (r) => r.fulfill(json([])));
  await page.route(`${B}/**/billing/audit`, (r) => r.fulfill(json([])));
}

/** Seed the auth tokens the app checks before mounting /app/* shells. */
export async function seedAuth(page: Page, baseURL: string) {
  await page.addInitScript(
    ([cid]) => {
      window.localStorage.setItem("va_token", "test-access");
      window.localStorage.setItem("va_refresh_token", "test-refresh");
      window.localStorage.setItem("va_company_id", cid);
      window.localStorage.setItem("va_remember", "1");
    },
    [COMPANY_ID],
  );
}

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page, baseURL }, use) => {
    await mockApi(page);
    await seedAuth(page, baseURL!);
    await use(page);
  },
});

export { expect, COMPANY_ID };
