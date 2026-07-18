import { test, expect } from "./fixtures";

/**
 * Report PDF download must surface the REAL backend error (Task: PDF pipeline
 * fix) — e.g. the 403 plan-gate message — instead of the old generic
 * "report failed". We mock the export endpoint returning the real 403 envelope.
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "*",
};
const REAL_MSG = "the 'exports' feature isn't available on your current plan — upgrade to access it";

test.describe("reports", () => {
  test("surfaces the real backend error on a failed PDF download", async ({ authedPage: page }) => {
    await page.route(`**/localhost:8000/projects/*/report.pdf*`, (route) => {
      if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS, body: "" });
      return route.fulfill({
        status: 403, contentType: "application/json", headers: CORS,
        body: JSON.stringify({ error: { code: "FORBIDDEN", message: REAL_MSG, request_id: "test-req" } }),
      });
    });

    await page.goto("/app/reports");
    await page.getByRole("button", { name: "Download PDF", exact: true }).first().click();

    // The actionable backend message is shown; the old generic string is not.
    await expect(page.getByText(/exports.*feature isn't available on your current plan/i)).toBeVisible();
    await expect(page.getByText("report failed")).toHaveCount(0);
  });
});
