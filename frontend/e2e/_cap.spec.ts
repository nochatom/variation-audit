import { test } from "./fixtures";
test("cap tech", async ({ authedPage }) => {
  await authedPage.setViewportSize({ width: 1000, height: 1200 });
  await authedPage.goto("/app/analysis");
  await authedPage.locator("summary").first().click();
  await authedPage.getByRole("button", { name: /Show technical details/i }).click();
  await authedPage.waitForTimeout(300);
  await authedPage.screenshot({ path: "cap-tech.png", fullPage: true });
});
