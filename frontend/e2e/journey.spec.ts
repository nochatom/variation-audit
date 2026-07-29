import { test, expect, mockApi } from "./fixtures";

/**
 * Critical user journey, end-to-end through the real UI with the backend
 * mocked at the network layer: login → dashboard → create project →
 * upload contract → open the billing plan modal. This is the path a UI
 * regression is most likely to break, so it gates every PR.
 */

test.describe("critical journey", () => {
  test("login form authenticates and lands on the dashboard", async ({ page }) => {
    await mockApi(page); // login is a public-page flow, mock the API directly
    await page.goto("/login");

    await page.getByPlaceholder(/name@company/i).fill("demo@variationiq.com");
    await page.getByPlaceholder("••••••••").fill("Demo1234!");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(page).toHaveURL(/\/app\/dashboard/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("dashboard renders the authenticated shell", async ({ authedPage }) => {
    await authedPage.goto("/app/dashboard");
    await expect(authedPage.getByRole("heading", { level: 1 })).toBeVisible();
    // On mobile the sidebar is behind the menu drawer; open it first so the
    // nav is reachable (desktop shows it inline). Either way the canonical
    // chrome must expose the same navigation.
    const menuButton = authedPage.getByRole("button", { name: /Open menu/i });
    if (await menuButton.isVisible()) await menuButton.click();
    // The desktop sidebar is always in the DOM (hidden on mobile) and the
    // mobile drawer adds a second copy — target the visible one regardless
    // of viewport.
    await expect(authedPage.locator('a[href="/app/projects"]').filter({ visible: true }).first()).toBeVisible();
    await expect(authedPage.locator('a[href="/app/documents"]').filter({ visible: true }).first()).toBeVisible();
  });

  test("create a project", async ({ authedPage }) => {
    await authedPage.goto("/app/projects");
    await authedPage.getByRole("button", { name: "New project", exact: true }).click();
    await authedPage.getByPlaceholder(/Sydney Metro/i).fill("E2E Test Project");
    await authedPage.getByRole("button", { name: "Create project", exact: true }).click();
    // No error surfaced — the create call resolved (mocked 201).
    await expect(authedPage.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("upload a contract on the Documents page", async ({ authedPage }) => {
    await authedPage.goto("/app/documents");
    // The contract UploadCard's hidden file input (accept=".pdf,.txt").
    const contractCard = authedPage.getByText(/No scope baseline yet|Scope baseline/i).locator("xpath=ancestor::*[.//input[@type='file']][1]");
    await contractCard.locator('input[type="file"]').setInputFiles({
      name: "contract.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Agreed scope baseline: electrical rough-in and fit-off."),
    });
    await expect(authedPage.getByText(/Scope baseline in place/i)).toBeVisible();
  });

  test("open the billing plan modal", async ({ authedPage }) => {
    await authedPage.goto("/app/settings/billing");
    // Free plan → button reads "Upgrade plan"; opens the UpgradeModal.
    await authedPage.getByRole("button", { name: /Upgrade plan|Change plan/i }).first().click();
    const dialog = authedPage.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(/Change plan/i);
    // Modal closes cleanly (exit animation + unmount).
    await authedPage.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toBeHidden();
  });
});
