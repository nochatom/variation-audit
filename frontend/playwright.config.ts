import { defineConfig, devices } from "@playwright/test";

/**
 * E2E smoke + a11y + visual-regression config.
 *
 * Deliberately independent of the backend/engine/Postgres: every
 * authenticated journey mocks the API at the network layer (see
 * e2e/fixtures.ts), so this whole suite is deterministic and fast enough to
 * gate every PR. It verifies the *frontend* — the exact thing UI changes can
 * break — not backend behaviour, which has its own pytest suite.
 *
 * Vitest (tests/**) and Playwright (e2e/**) stay fully separate: different
 * dirs, different runners, no overlap.
 */
const PORT = Number(process.env.E2E_PORT || 3100);
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  timeout: 30_000,
  expect: {
    // Cross-OS font rendering differs slightly (Windows vs the Linux CI
    // runner) — a small tolerance keeps visual regression meaningful without
    // being flaky. Real regressions move far more than 2% of pixels.
    toHaveScreenshot: { maxDiffPixelRatio: 0.02, animations: "disabled", caret: "hide" },
  },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
  // Starts a production build's server on a dedicated port. CI builds in a
  // separate step, so there `next start` is instant. Locally we build first —
  // otherwise `next start` serves a STALE bundle and tests run against
  // pre-edit code (a real trap: green tests can hide un-served changes).
  webServer: {
    command: process.env.CI
      ? `npx next start --port ${PORT}`
      : `npx next build && npx next start --port ${PORT}`,
    url: BASE_URL,
    // Locally we must NOT reuse an already-running (possibly stale) server —
    // that would skip the build above. Reuse only when explicitly opted in
    // (E2E_REUSE_SERVER=1) for fast iteration against a known-fresh build.
    reuseExistingServer: !process.env.CI && process.env.E2E_REUSE_SERVER === "1",
    // Build + start can exceed the default 2 min on a cold Next build.
    timeout: 300_000,
  },
});
