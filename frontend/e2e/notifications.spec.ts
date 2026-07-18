import { test, expect } from "./fixtures";

/**
 * Notifications UI regressions (fixed this cycle):
 *   1. Rows must render a HUMAN message per type — never the raw payload UUIDs.
 *   2. Marking all read must clear the topbar bell badge immediately, without
 *      a route change (the page broadcasts `notifications:changed`).
 * Backend behaviour is covered by pytest; here we mock it at the network layer.
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "*",
};
const PROJECT_UUID = "d67b9cfc-6867-4d43-996c-be5834436809";
const JOB_UUID = "6bffc96b-ca7d-47f6-a853-650c4ec54ed8";

test.describe("notifications", () => {
  test("renders human messages (not raw UUIDs) and clears the bell on mark-all-read", async ({ authedPage: page }) => {
    // Stateful mocks: read-all flips everything to read + zeroes the count,
    // exactly like the backend, so the badge-sync path is exercised for real.
    let unread = 2;
    const items = () => [
      { id: "n1", type: "analysis_complete", payload: { job_id: JOB_UUID, project_id: PROJECT_UUID }, read: unread === 0, created_at: "2026-07-14T16:15:45Z" },
      { id: "n2", type: "analysis_failed", payload: { code: "INTERNAL", job_id: JOB_UUID, retryable: true, project_id: PROJECT_UUID }, read: unread === 0, created_at: "2026-07-12T15:14:39Z" },
    ];

    await page.route("**/localhost:8000/notifications/unread-count", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify({ count: unread }) });
    });
    await page.route("**/localhost:8000/notifications/read-all", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      unread = 0;
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify({ marked: 2 }) });
    });
    await page.route("**/localhost:8000/notifications*", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify(items()) });
    });

    await page.goto("/app/notifications");

    // 1. Human messages, and the raw UUIDs are NOT shown as text.
    await expect(page.getByText("Analysis complete", { exact: true })).toBeVisible();
    await expect(page.getByText("Analysis failed", { exact: true })).toBeVisible();
    await expect(page.getByText(/Error INTERNAL/)).toBeVisible();
    await expect(page.getByText(PROJECT_UUID)).toHaveCount(0);
    await expect(page.getByText(JOB_UUID)).toHaveCount(0);

    // 2. Bell badge (topbar) is showing before, gone after mark-all-read.
    const bellDot = page.locator('[aria-label="Notifications"] .bg-ip-orange');
    await expect(bellDot).toBeVisible();

    await page.getByRole("button", { name: "Mark all read", exact: true }).click();

    await expect(bellDot).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark all read", exact: true })).toHaveCount(0);
  });

  test("opening the bell popover does not change the active sidebar item", async ({ authedPage: page }) => {
    await page.route("**/localhost:8000/notifications/unread-count", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify({ count: 1 }) });
    });
    await page.route("**/localhost:8000/notifications*", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify([]) });
    });

    await page.goto("/app/dashboard");
    // Attribute-level checks (work regardless of sidebar visibility per viewport).
    const dashActive = page.locator('a[href="/app/dashboard"][aria-current="page"]');
    const notifActive = page.locator('a[href="/app/notifications"][aria-current="page"]');
    await expect(dashActive).toHaveCount(1);
    await expect(notifActive).toHaveCount(0);

    // Open the bell popover — this must NOT navigate or change the active item.
    await page.getByRole("button", { name: "Notifications", exact: true }).click();
    await expect(page.getByText("View all notifications")).toBeVisible();
    await expect(page).toHaveURL(/\/app\/dashboard/);
    await expect(dashActive).toHaveCount(1);
    await expect(notifActive).toHaveCount(0);

    // Close it (Escape) — Dashboard is still the active item.
    await page.keyboard.press("Escape");
    await expect(page.getByText("View all notifications")).toHaveCount(0);
    await expect(dashActive).toHaveCount(1);
    await expect(notifActive).toHaveCount(0);
  });

  test('bell popover "Mark all as read" clears the badge and disables when none unread', async ({ authedPage: page }) => {
    let unread = 2;
    const items = () => [
      { id: "n1", type: "analysis_complete", payload: { project_id: PROJECT_UUID }, read: unread === 0, created_at: "2026-07-14T16:15:45Z" },
      { id: "n2", type: "analysis_failed", payload: { code: "INTERNAL", project_id: PROJECT_UUID }, read: unread === 0, created_at: "2026-07-12T15:14:39Z" },
    ];
    await page.route("**/localhost:8000/notifications/unread-count", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify({ count: unread }) });
    });
    await page.route("**/localhost:8000/notifications/read-all", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      unread = 0;
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify({ marked: 2 }) });
    });
    await page.route("**/localhost:8000/notifications*", (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify(items()) });
    });

    await page.goto("/app/dashboard");
    const bellDot = page.locator('[aria-label="Notifications"] .bg-ip-orange');
    await expect(bellDot).toBeVisible();

    // Open the popover; the action is enabled while there are unread items.
    await page.getByRole("button", { name: "Notifications", exact: true }).click();
    const markAll = page.getByRole("button", { name: "Mark all as read" });
    await expect(markAll).toBeEnabled();

    await markAll.click();

    // Badge clears immediately and the action disables (nothing left unread).
    await expect(bellDot).toHaveCount(0);
    await expect(markAll).toBeDisabled();
  });
});
