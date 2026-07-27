import { describe, expect, it } from "vitest";
import { bindingLimit, limitRows, resetsAt } from "../lib/billing/limits";
import { Usage } from "../lib/billing/api";

function usage(over: Partial<Usage> = {}): Usage {
  return {
    plan: "free",
    period_start: "2026-07-01T00:00:00+00:00",
    projects_active: 0,
    projects_limit: 1,
    documents_processed: 0,
    documents_limit: 20,
    analysis_runs: 0,
    analysis_runs_limit: 5,
    seats_limit: 3,
    ...over,
  } as Usage;
}

describe("limitRows", () => {
  it("sorts the most pressured limit first", () => {
    // documents mildly used, projects at limit, analysis runs over
    const rows = limitRows(usage({
      analysis_runs: 13, projects_active: 1, documents_processed: 4,
    }));
    expect(rows.map((r) => r.key)).toEqual(["analysis_runs", "projects", "documents"]);
    expect(rows[0].state).toBe("over");
    expect(rows[1].state).toBe("at");
    expect(rows[2].state).toBe("ok");
  });

  it("ranks state before ratio", () => {
    // documents at 95% has a higher ratio than projects at 100%, but "at"
    // outranks "near" because it is actually blocking.
    const rows = limitRows(usage({
      projects_active: 1, documents_processed: 19, analysis_runs: 0,
    }));
    expect(rows[0].key).toBe("projects");
    expect(rows[1].key).toBe("documents");
    expect(rows[1].state).toBe("near");
  });

  it("sorts unlimited last regardless of raw usage", () => {
    const rows = limitRows(usage({
      analysis_runs: 9999, analysis_runs_limit: null,
      projects_active: 1, documents_processed: 1,
    }));
    expect(rows[rows.length - 1].key).toBe("analysis_runs");
    expect(rows[rows.length - 1].state).toBe("unlimited");
    expect(rows[rows.length - 1].ratio).toBe(-1);
  });

  it("never reports a negative remaining", () => {
    const rows = limitRows(usage({ analysis_runs: 13 }));
    expect(rows[0].remaining).toBe(0);
  });

  it("treats a zero limit with usage as over, not NaN", () => {
    const rows = limitRows(usage({ projects_active: 2, projects_limit: 0 }));
    const projects = rows.find((r) => r.key === "projects")!;
    expect(projects.state).toBe("over");
    expect(Number.isNaN(projects.ratio)).toBe(false);
  });
});

describe("bindingLimit", () => {
  it("returns the blocking limit when one is over", () => {
    expect(bindingLimit(usage({ analysis_runs: 13 }))?.key).toBe("analysis_runs");
  });

  it("returns the limit that is exactly at cap", () => {
    expect(bindingLimit(usage({ projects_active: 1 }))?.key).toBe("projects");
  });

  it("stays silent at 'near' — warning every visit trains people to ignore it", () => {
    expect(bindingLimit(usage({ documents_processed: 19 }))).toBeNull();
  });

  it("returns null for a healthy org", () => {
    expect(bindingLimit(usage())).toBeNull();
  });

  it("returns null when everything is unlimited", () => {
    expect(bindingLimit(usage({
      analysis_runs: 500, analysis_runs_limit: null,
      projects_active: 40, projects_limit: null,
      documents_processed: 900, documents_limit: null,
    }))).toBeNull();
  });
});

describe("resetsAt", () => {
  it("rolls to the first of the following month", () => {
    expect(resetsAt(usage()).toISOString()).toBe("2026-08-01T00:00:00.000Z");
  });

  it("rolls across a year boundary", () => {
    const d = resetsAt(usage({ period_start: "2026-12-01T00:00:00+00:00" }));
    expect(d.toISOString()).toBe("2027-01-01T00:00:00.000Z");
  });
});
