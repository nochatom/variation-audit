"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, FileText, Lock } from "lucide-react";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useFeatures } from "@/lib/billing/hooks";
import { PageHeader, Card, ErrorNote, Spinner, EmptyState, aud } from "@/components/ui";

type Scope = "confirmed" | "pending";

const SCOPES: { id: Scope; label: string; note: string }[] = [
  { id: "confirmed", label: "Approved only", note: "The claimable position — approved variations only." },
  { id: "pending", label: "Draft (pending)", note: "Under review, not yet approved. For internal use." },
];

export default function ReportsPage() {
  const { companyId, isAdmin } = useApp();
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("confirmed");

  // Plan capability flags — the endpoint is admin-only, so for non-admins this
  // stays null and we let the 403 on download carry the message instead.
  const { data: features } = useFeatures(isAdmin ? companyId : null);
  const exportsLocked = features ? !features.exports : false;

  useEffect(() => {
    if (!companyId) return;
    api.orgDashboard(companyId).then(setData).catch((e) => setError(e.message));
  }, [companyId]);

  async function download(projectId: string, projectName: string) {
    setBusy(projectId);
    setError(null);
    try {
      const blob = await api.reportPdf(projectId, scope);
      // An anchor with `download` respects the filename and survives popup
      // blockers, and the object URL is released rather than leaked.
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${projectName.replace(/[^\w\-]+/g, "-").toLowerCase()}-${scope}-report.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(
        e?.status === 403
          ? "PDF export isn't included in your current plan. Upgrade to generate reports."
          : e.message,
      );
    } finally {
      setBusy(null);
    }
  }

  const projects = data?.projects ?? [];
  const totalReportable = projects.reduce((s, p) => s + p.recoverable_confirmed, 0);

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Generate a review-ready recovery report for any project."
      />

      {error && <ErrorNote message={error} />}

      {/* ---- Conditional escalation: when the plan can't export, nothing else
           on this page is actionable, so the upgrade takes the whole page. ---- */}
      {exportsLocked ? (
        <div className="ip-card-lg p-8 sm:p-10">
          <Lock className="h-6 w-6 text-ip-orange-2" aria-hidden />
          <h2 className="mt-3 text-[20px] font-bold tracking-display text-ip-ink">
            PDF export isn&apos;t on your plan
          </h2>
          <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-ip-ink-2">
            Your findings and approvals are unaffected — only the exported report is gated.
            {totalReportable > 0 && (
              <>
                {" "}
                You currently have{" "}
                <span className="font-bold tabular-nums text-ip-recovery">{aud(totalReportable)}</span>{" "}
                of approved value ready to report on.
              </>
            )}
          </p>
          <Link href="/app/settings/billing" className="btn-orange mt-6">
            View plans
          </Link>
        </div>
      ) : (
        <>
          {!data && !error && <Spinner />}

          {data && projects.length === 0 && (
            <EmptyState
              title="No projects to report on"
              body="Create a project and run analysis to generate a report."
              action={<Link href="/app/projects" className="btn-orange">Create project</Link>}
            />
          )}

          {data && projects.length > 0 && (
            <>
              {/* Report scope — the endpoint has always accepted review_status;
                  the UI simply never offered it. A draft over pending findings
                  is how a QS sanity-checks a claim before it goes out. */}
              <div className="mb-5">
                <h2 className="ip-label mb-2">Report scope</h2>
                <div className="flex w-fit gap-1 rounded-md border border-ip-line bg-ip-card p-1" role="group" aria-label="Report scope">
                  {SCOPES.map((s) => (
                    <button
                      key={s.id}
                      aria-pressed={scope === s.id}
                      onClick={() => setScope(s.id)}
                      className={`rounded-xs px-3.5 py-1.5 text-sm font-semibold transition-colors ${
                        scope === s.id ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-[13px] text-ip-ink-2">
                  {SCOPES.find((s) => s.id === scope)!.note}
                </p>
              </div>

              <Card className="divide-y divide-ip-line">
                {projects.map((p) => {
                  const count = scope === "confirmed" ? p.counts.confirmed : p.counts.pending;
                  const empty = count === 0;
                  return (
                    <div
                      key={p.id}
                      className="flex flex-wrap items-center gap-4 px-4 py-4 transition-colors hover:bg-ip-card-2"
                    >
                      <FileText
                        className={`h-4 w-4 shrink-0 ${empty ? "text-ip-ink-3" : "text-ip-navy"}`}
                        aria-hidden
                      />

                      <div className="min-w-[180px] flex-1">
                        <Link
                          href={`/app/projects/${p.id}`}
                          className="text-[14px] font-semibold text-ip-ink hover:text-ip-navy"
                        >
                          {p.name}
                        </Link>
                        <div className="mt-0.5 text-[12px] text-ip-ink-3">
                          {empty
                            ? `Nothing ${scope} to report`
                            : `${count} ${scope} ${count === 1 ? "variation" : "variations"}`}
                        </div>
                      </div>

                      {/* Only the approved scope carries a claimable figure —
                          pending value isn't money, it's a proposition. */}
                      {scope === "confirmed" && (
                        <div className="shrink-0 text-right">
                          <div
                            className={`text-[18px] font-bold leading-none tabular-nums tracking-display ${
                              empty ? "text-ip-ink-3" : "text-ip-recovery"
                            }`}
                          >
                            {aud(p.recoverable_confirmed)}
                          </div>
                          <div className="mt-1 text-[11px] text-ip-ink-3">approved</div>
                        </div>
                      )}

                      <button
                        onClick={() => download(p.id, p.name)}
                        disabled={busy === p.id || empty}
                        aria-label={`Download ${scope} report for ${p.name}`}
                        title={empty ? `No ${scope} variations to include` : undefined}
                        className="btn-ghost shrink-0"
                      >
                        <Download className="h-3.5 w-3.5" aria-hidden />
                        {busy === p.id ? "Generating…" : "PDF"}
                      </button>
                    </div>
                  );
                })}
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
