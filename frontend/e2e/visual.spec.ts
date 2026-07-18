import { test, expect } from "./fixtures";

/**
 * Basic visual regression for the main pages. Playwright freezes CSS
 * animations for screenshots (config: animations: "disabled") so entrance
 * motion never causes flake, and a 2% pixel tolerance absorbs cross-OS font
 * rendering. Baselines are per-project (desktop + mobile) and per-OS —
 * generate them in the same environment the gate runs in (the Linux CI
 * runner) with `npm run e2e:update`, then commit e2e/__screenshots__.
 *
 * Public pages only: they're stable and don't depend on mocked data timing,
 * which keeps the visual baselines meaningful rather than noisy.
 */

const PAGES: { path: string; name: string }[] = [
  { path: "/", name: "landing" },
  { path: "/login", name: "login" },
  { path: "/pricing", name: "pricing" },
];

for (const { path, name } of PAGES) {
  test(`visual: ${name}`, { tag: "@visual" }, async ({ page }) => {
    await page.goto(path);
    // Let fonts settle and any first-paint entrance animation reach its
    // resting state before snapshotting.
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: true });
  });
}
