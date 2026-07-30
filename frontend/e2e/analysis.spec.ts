import { test, expect } from "./fixtures";

/**
 * Analysis page consumes the backend SSE progress stream (Task 4): the
 * progress %, stats, and live log must all update from real events — nothing
 * is fabricated client-side. We mock a running job and a stubbed event stream
 * and assert the UI reflects the stream's final event.
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "*",
};
// Must match ORG_DASHBOARD.projects[0].id in fixtures.ts.
const PROJECT_ID = "33333333-3333-4333-8333-333333333333";
const JOB_ID = "job-live-1";

// Three real-shaped events: mid-run → detection → terminal. The client stops
// on the terminal (Completed / 100%) event.
function sseBody(): string {
  const ev = (o: Record<string, unknown>) => `id: ${o.seq}\nevent: progress\ndata: ${JSON.stringify(o)}\n\n`;
  const base = { current_document: null, processed_documents: 3, total_documents: 3 };
  return (
    ev({ ...base, seq: 1, stage: "AI Analysis", status: "running", percentage: 47, variations_found: 0, evidence_links: 0, elapsed_seconds: 5, estimated_remaining: 5 }) +
    ev({ ...base, seq: 2, stage: "Variation Detection", status: "completed", percentage: 68, variations_found: 5, evidence_links: 13, elapsed_seconds: 10, estimated_remaining: 4 }) +
    ev({ ...base, seq: 3, stage: "Completed", status: "completed", percentage: 100, variations_found: 5, evidence_links: 13, elapsed_seconds: 12, estimated_remaining: 0 })
  );
}

// Failed transition: two completed stages, then AI Analysis fails.
function sseFailBody(): string {
  const ev = (o: Record<string, unknown>) => `id: ${o.seq}\nevent: progress\ndata: ${JSON.stringify(o)}\n\n`;
  const base = { current_document: null, processed_documents: 3, total_documents: 3, variations_found: 0, evidence_links: 0 };
  return (
    ev({ ...base, seq: 1, stage: "Queue", status: "completed", percentage: 5, elapsed_seconds: 0, estimated_remaining: 0 }) +
    ev({ ...base, seq: 2, stage: "Loading Documents", status: "completed", percentage: 15, elapsed_seconds: 0.1, estimated_remaining: 0.4 }) +
    ev({ ...base, seq: 3, stage: "AI Analysis", status: "running", percentage: 47, elapsed_seconds: 0.2, estimated_remaining: 0.3 }) +
    ev({ ...base, seq: 4, stage: "AI Analysis", status: "failed", percentage: 47, elapsed_seconds: 359, estimated_remaining: 405 })
  );
}

test.describe("analysis (live SSE)", () => {
  test("progress, stats and live log update from backend events", async ({ authedPage: page }) => {
    // Per-project dashboard: a job in-flight so the page arms the SSE stream.
    await page.route(`**/localhost:8000/projects/*/dashboard`, (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({
        status: 200, contentType: "application/json", headers: CORS,
        body: JSON.stringify({
          project: { id: PROJECT_ID, name: "Sydney Metro — Package 4", state: "NSW", status: "in_progress", has_contract: true },
          counts: { pending: 4, confirmed: 6, rejected: 2, total: 12 },
          recoverable_confirmed: 284500, time_bar_at_risk: 3, document_count: 3,
          latest_job: { id: JOB_ID, status: "running", recoverable_total: null },
        }),
      });
    });
    // The SSE endpoint — EventSource GET (no preflight); stream the events.
    await page.route(`**/localhost:8000/projects/*/analysis/*/events*`, (route) =>
      route.fulfill({ status: 200, contentType: "text/event-stream", headers: CORS, body: sseBody() }),
    );

    await page.goto("/app/analysis");

    // Percentage + terminal state derived from the last event.
    await expect(page.getByText("100%").first()).toBeVisible();
    await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible();

    // Real stats straight off the events (label → sibling value).
    await expect(page.getByText("Variations detected").locator("xpath=following-sibling::div")).toHaveText("5");
    await expect(page.getByText("Evidence collected").locator("xpath=following-sibling::div")).toHaveText("13");
    await expect(page.getByText("Documents processed").locator("xpath=following-sibling::div")).toHaveText("3/3");

    // Live log rendered one line per event, derived from real fields.
    await expect(page.getByText("Live log")).toBeVisible();
    await expect(page.getByText("Variation Detection completed (5 found)")).toBeVisible();
  });

  test("a queued job shows 'Queued', never a fake 'Uploading documents' stage", async ({ authedPage: page }) => {
    // Latest job is QUEUED (not yet claimed by a worker).
    await page.route(`**/localhost:8000/projects/*/dashboard`, (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({
        status: 200, contentType: "application/json", headers: CORS,
        body: JSON.stringify({
          project: { id: PROJECT_ID, name: "Sydney Metro — Package 4", state: "NSW", status: "in_progress", has_contract: true },
          counts: { pending: 4, confirmed: 6, rejected: 2, total: 12 },
          recoverable_confirmed: 284500, time_bar_at_risk: 3, document_count: 3,
          latest_job: { id: JOB_ID, status: "queued", recoverable_total: null },
        }),
      });
    });
    // A queued job has no events — the SSE stream connects but delivers none.
    await page.route(`**/localhost:8000/projects/*/analysis/*/events*`, (route) =>
      route.fulfill({ status: 200, contentType: "text/event-stream", headers: CORS, body: ": connected\n\n" }),
    );

    await page.goto("/app/analysis");

    // Honest queued state: the current label reflects the real backend status…
    await expect(page.getByText("Queued — waiting for an available worker")).toBeVisible();
    await expect(page.getByText("Queued", { exact: true }).first()).toBeVisible(); // status badge
    await expect(page.getByText("0%", { exact: true })).toBeVisible(); // no fabricated percentage
    // …and the OLD fabricated in-flight states must NOT appear for a queued job.
    await expect(page.getByText("Starting…")).toHaveCount(0);
    await expect(page.getByText("Waiting for first progress event…")).toHaveCount(0);
  });

  test("Stop Analysis: button appears while running, confirms, cancels, shows Cancelled", async ({ authedPage: page }) => {
    let cancelled = false;
    let cancelCalled = false;
    await page.route(`**/localhost:8000/projects/*/dashboard`, (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({
        status: 200, contentType: "application/json", headers: CORS,
        body: JSON.stringify({
          project: { id: PROJECT_ID, name: "Sydney Metro — Package 4", state: "NSW", status: "in_progress", has_contract: true },
          counts: { pending: 4, confirmed: 6, rejected: 2, total: 12 },
          recoverable_confirmed: 284500, time_bar_at_risk: 3, document_count: 3,
          latest_job: { id: JOB_ID, status: cancelled ? "cancelled" : "running", recoverable_total: null },
        }),
      });
    });
    // Minimal live stream: connected, no events → the panel shows the running
    // status and the Stop button (from persisted status).
    await page.route(`**/localhost:8000/projects/*/analysis/*/events*`, (route) =>
      route.fulfill({ status: 200, contentType: "text/event-stream", headers: CORS, body: ": connected\n\n" }),
    );
    // The REAL cancel endpoint — must actually be hit (not a fake button).
    await page.route(`**/localhost:8000/projects/*/analysis/*/cancel`, (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      cancelCalled = true;
      cancelled = true;
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS,
        body: JSON.stringify({ job_id: JOB_ID, status: "running" }) });
    });

    await page.goto("/app/analysis");

    const stop = page.getByRole("button", { name: "Stop Analysis" });
    await expect(stop).toBeVisible();
    await stop.click();

    // Confirmation dialog with the exact required copy.
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Are you sure you want to stop this analysis?")).toBeVisible();
    await dialog.getByRole("button", { name: "Stop analysis", exact: true }).click();

    // The real cancel API was called and the UI reflects Cancelled.
    await expect.poll(() => cancelCalled).toBe(true);
    await expect(page.getByText("Cancelled", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop Analysis" })).toHaveCount(0);
  });

  test("a failed stage shows red + overall Failed + the real reason, and stops progress (Running → Failed)", async ({ authedPage: page }) => {
    const ERROR = "engine connection failed after 2 attempts";
    // Stateful dashboard: running first (arms the stream), then failed with the
    // real error after the SSE 'failed' event triggers a reload.
    let dashCalls = 0;
    await page.route(`**/localhost:8000/projects/*/dashboard`, (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      dashCalls += 1;
      const failed = dashCalls >= 2;
      return route.fulfill({
        status: 200, contentType: "application/json", headers: CORS,
        body: JSON.stringify({
          project: { id: PROJECT_ID, name: "Sydney Metro — Package 4", state: "NSW", status: "in_progress", has_contract: true },
          counts: { pending: 4, confirmed: 6, rejected: 2, total: 12 },
          recoverable_confirmed: 284500, time_bar_at_risk: 3, document_count: 3,
          latest_job: failed
            ? { id: JOB_ID, status: "failed", recoverable_total: null, error_code: "ENGINE_UNAVAILABLE", error_message: ERROR, error_retryable: true }
            : { id: JOB_ID, status: "running", recoverable_total: null },
        }),
      });
    });
    await page.route(`**/localhost:8000/projects/*/analysis/*/events*`, (route) =>
      route.fulfill({ status: 200, contentType: "text/event-stream", headers: CORS, body: sseFailBody() }),
    );

    await page.goto("/app/analysis");

    // Red failed indicator, overall Failed, the failed stage, and the REAL reason.
    await expect(page.getByText("Analysis failed", { exact: true })).toBeVisible();     // failure banner
    await expect(page.getByText("Failed", { exact: true }).first()).toBeVisible();      // overall status badge
    await expect(page.getByText(/Failed stage:/)).toBeVisible();
    await expect(page.getByText(new RegExp(ERROR))).toBeVisible();                      // real backend reason

    // Progress is stopped — no running/spinner state lingers.
    await expect(page.getByText("In progress")).toHaveCount(0);
    await expect(page.getByText("Starting…")).toHaveCount(0);

    // Subsequent stages did NOT fabricate completion — Evidence Linking is still pending.
    await page.locator("summary").click();
    await page.getByRole("button", { name: /Show technical details/ }).click();
    const evidenceRow = page.getByText("Evidence Linking").locator("xpath=ancestor::li[1]");
    await expect(evidenceRow).toContainText("pending");
    const aiRow = page.getByText("AI Analysis", { exact: true }).locator("xpath=ancestor::li[1]");
    await expect(aiRow).toContainText("failed");
  });
});
