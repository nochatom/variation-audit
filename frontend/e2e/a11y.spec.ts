import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

/**
 * Accessibility regression gate. Runs axe-core (WCAG 2.0/2.1 A + AA) against
 * each key page and fails on any serious/critical violation. Public pages use
 * a plain page; authenticated pages use the mocked-auth fixture so the real
 * app shell is audited, not a redirect.
 *
 * We scope to serious+critical to keep the gate meaningful and non-flaky —
 * it catches genuine regressions (missing labels, contrast failures, broken
 * roles) without failing on debatable minor items.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/**
 * Documented, explicit baseline exceptions — pre-existing items that are a
 * brand/design decision for the design team, NOT test blind spots. Kept
 * here (visible, greppable) rather than silently suppressed, and scoped as
 * tightly as possible so the gate still catches every *new* regression.
 *
 * - `.btn-orange`: white text on the vibrant brand orange (#ff7a26) is 2.6:1.
 *   Any vibrant orange fundamentally cannot carry white text at AA — making
 *   it pass needs a materially darker "burnt orange", a brand-identity change
 *   that belongs to the design team, not this test PR. Flagged for their call.
 */
const KNOWN_EXCEPTIONS: { rule: string; targetIncludes: string }[] = [
  { rule: "color-contrast", targetIncludes: "btn-orange" },
];

function isKnownException(ruleId: string, target: string): boolean {
  return KNOWN_EXCEPTIONS.some((e) => e.rule === ruleId && target.includes(e.targetIncludes));
}

async function auditSeriousViolations(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const serious = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      targets: v.nodes
        .map((n) => ({ target: n.target.join(" "), summary: n.failureSummary?.split("\n")[1]?.trim() }))
        .filter((t) => !isKnownException(v.id, t.target)),
    }))
    // drop a violation entirely once all its nodes are documented exceptions
    .filter((v) => v.targets.length > 0);
  return serious;
}

test.describe("accessibility (public)", () => {
  for (const path of ["/", "/login", "/pricing"]) {
    test(`no serious/critical axe violations on ${path}`, async ({ page }) => {
      await page.goto(path);
      const violations = await auditSeriousViolations(page);
      expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
    });
  }
});

test.describe("accessibility (authenticated)", () => {
  test("no serious/critical axe violations on the dashboard", async ({ authedPage }) => {
    await authedPage.goto("/app/dashboard");
    await expect(authedPage.getByRole("heading", { level: 1 })).toBeVisible();
    const violations = await auditSeriousViolations(authedPage);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });
});
