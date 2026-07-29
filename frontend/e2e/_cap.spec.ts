import { test } from "./fixtures";
test("cap tech", async ({ authedPage }) => {
  await authedPage.setViewportSize({ width: 1000, height: 1200 });
  await authedPage.goto("/app/analysis");
  await authedPage.waitForLoadState("networkidle");
  await authedPage.getByText("Technical detail").first().click();
  await authedPage.getByRole("button", { name: /Show technical details/i }).click();
  await authedPage.waitForTimeout(300);
  await authedPage.screenshot({ path: "cap-tech.png", fullPage: true });
});
