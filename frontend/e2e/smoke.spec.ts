import { test, expect } from "@playwright/test";

/**
 * Smoke tests — public pages render, key content is present, and navigation
 * works. Runs on both the desktop-chromium and mobile-chromium projects
 * (see playwright.config.ts), so every assertion is implicitly a
 * responsive-viewport check too.
 */

test.describe("landing page", () => {
  test("renders hero, brand, and primary CTAs", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/VariationiQ/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/variation revenue/i);
    // Brand mark + wordmark (canonical LogoMark).
    await expect(page.getByRole("link", { name: /VariationiQ home/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /Start Free Analysis/i }).first()).toBeVisible();
  });

  test("has no horizontal overflow", async ({ page }) => {
    await page.goto("/");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1); // sub-pixel rounding tolerated
  });
});

test.describe("navigation", () => {
  test("landing → pricing → login are reachable", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Pricing", exact: true }).first().click();
    await expect(page).toHaveURL(/\/pricing/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    await page.goto("/pricing");
    await page.getByRole("link", { name: /Sign in|Get started/i }).first().click();
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe("login page", () => {
  test("renders login/signup toggle and form with ARIA attributes", async ({ page }) => {
    await page.goto("/login");
    const group = page.getByRole("group", { name: "Form mode" });
    await expect(group).toBeVisible();
    const loginBtn = group.getByRole("button", { name: "Log in", exact: true });
    const signupBtn = group.getByRole("button", { name: "Sign up", exact: true });
    await expect(loginBtn).toHaveAttribute("aria-pressed", "true");
    await expect(signupBtn).toHaveAttribute("aria-pressed", "false");

    await expect(page.getByPlaceholder(/name@company/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Sign in with Google/i })).toBeVisible();
  });

  test("toggling to Sign up reveals the organization field and updates ARIA pressed", async ({ page }) => {
    await page.goto("/login");
    const group = page.getByRole("group", { name: "Form mode" });
    const loginBtn = group.getByRole("button", { name: "Log in", exact: true });
    const signupBtn = group.getByRole("button", { name: "Sign up", exact: true });

    await expect(page.getByPlaceholder(/Harbourside Electrical/i)).toBeHidden();
    await signupBtn.click();
    await expect(page.getByPlaceholder(/Harbourside Electrical/i)).toBeVisible();
    await expect(loginBtn).toHaveAttribute("aria-pressed", "false");
    await expect(signupBtn).toHaveAttribute("aria-pressed", "true");
  });
});

test.describe("pricing page", () => {
  test("renders plans, billing toggle, and Most Popular", async ({ page }) => {
    await page.goto("/pricing");
    const group = page.getByRole("group", { name: "Billing interval" });
    await expect(group).toBeVisible();
    const monthlyBtn = group.getByRole("button", { name: "Monthly", exact: true });
    const annualBtn = group.getByRole("button", { name: /Annual · 2 months free/i });
    await expect(monthlyBtn).toHaveAttribute("aria-pressed", "true");
    await expect(annualBtn).toHaveAttribute("aria-pressed", "false");

    await expect(page.getByText("Most Popular")).toBeVisible();
    await expect(page.getByRole("link", { name: "Contact Sales", exact: true }).first()).toBeVisible();
  });

  test("billing interval toggle switches price period and updates ARIA pressed", async ({ page }) => {
    await page.goto("/pricing");
    const group = page.getByRole("group", { name: "Billing interval" });
    const monthlyBtn = group.getByRole("button", { name: "Monthly", exact: true });
    const annualBtn = group.getByRole("button", { name: /Annual · 2 months free/i });

    await expect(page.getByText(/\/ month/i).first()).toBeVisible();
    await annualBtn.click();
    await expect(page.getByText(/\/ year/i).first()).toBeVisible();
    await expect(monthlyBtn).toHaveAttribute("aria-pressed", "false");
    await expect(annualBtn).toHaveAttribute("aria-pressed", "true");
  });
});
