"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, TriangleAlert, FileUp, ScanSearch } from "lucide-react";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, aud } from "@/components/ui";

export default function DashboardPage() {
  const { companyId } = useApp();
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    api.orgDashboard(companyId).then(setData).catch((e) => setError(e.message));
  }, [companyId]);

  const t = data?.totals;
  const atRisk = data?.projects.reduce((s, p) => s + p.time_bar_at_risk, 0) ?? 0;

  // The queue is the page's real content, so it earns a real ordering:
  // time-bar exposure first (money with a deadline), then review backlog.
  const queue = (data?.projects ?? [])
    .filter((p) => p.time_bar_at_risk > 0 || p.counts.pending > 0)
    .sort((a, b) => b.time_bar_at_risk - a.time_bar_at_risk || b.counts.pending - a.counts.pending);

  const hasProjects = (t?.projects ?? 0) > 0;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Your recovery position across every project, and what needs a decision today."
        actions={
          <Link href="/app/variations" className="btn-orange">
            Review variations
          </Link>
        }
      />

      {error && <ErrorNote message={error} />}
      {!data && !error && <Spinner />}

      {data && !hasProjects && <FirstRun />}

      {data && hasProjects && (
        <>
          {/* ---- Protagonist: the recovery position. One number, stated once,
               at a size nothing else on the page competes with. Supporting
               metrics live in a subordinate rail rather than as peer cards. ---- */}
          <section className="ip-card-lg mb-4 grid grid-cols-1 lg:grid-cols-[1.6fr_1fr]">
            <div className="p-6 sm:p-8">
              <h2 className="ip-label">Recoverable · confirmed</h2>
              <div className="mt-3 text-[44px] font-bold leading-none tabular-nums tracking-display text-ip-recovery sm:text-[56px]">
                {aud(t!.recoverable_confirmed)}
              </div>
              <p className="mt-3 max-w-md text-[13px] leading-relaxed text-ip-ink-2">
                Approved across {t!.projects} {t!.projects === 1 ? "project" : "projects"}. Pending
                variations are not counted until a reviewer confirms them.
              </p>
            </div>

            <dl className="grid grid-cols-3 border-t border-ip-line lg:grid-cols-1 lg:border-l lg:border-t-0">
              <Metric label="Pending review" value={String(t!.pending)} href="/app/variations" />
              <Metric label="Confirmed" value={String(t!.confirmed)} />
              <Metric label="Projects" value={String(t!.projects)} href="/app/projects" />
            </dl>
          </section>

          {/* ---- Conditional escalation: when nothing is time-barred this strip
               does not exist. An always-present "0 at risk" panel trains users
               to ignore the one element that must never be ignored. ---- */}
          {atRisk > 0 && (
            <Link
              href="/app/variations"
              className="ip-card-interactive mb-4 flex items-center gap-4 border-ip-risk/35 bg-ip-risk-bg p-4 sm:p-5"
            >
              <TriangleAlert className="h-5 w-5 shrink-0 text-ip-risk" aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="text-[15px] font-bold tracking-tight text-ip-ink">
                  {atRisk} {atRisk === 1 ? "variation is" : "variations are"} approaching a contractual
                  time bar
                </div>
                <div className="mt-0.5 text-[13px] text-ip-ink-2">
                  Entitlement lapses once the notice period expires. Review these first.
                </div>
              </div>
              <ArrowRight className="h-4 w-4 shrink-0 text-ip-risk" aria-hidden />
            </Link>
          )}

          {/* ---- The work queue, full width. This replaces the four-card
               "Workflows" grid, which only duplicated the sidebar. ---- */}
          <section>
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="ip-label">Needs a decision</h2>
              <Link
                href="/app/projects"
                className="text-[12px] font-semibold text-ip-navy transition-colors hover:text-ip-navy/75"
              >
                All projects
              </Link>
            </div>

            <Card className="divide-y divide-ip-line">
              {queue.length === 0 && (
                <div className="px-4 py-12 text-center">
                  <div className="text-sm font-semibold text-ip-ink">Everything is reviewed</div>
                  <div className="mt-1 text-[13px] text-ip-ink-2">
                    No pending variations and no time bars in range.
                  </div>
                </div>
              )}

              {queue.map((p) => (
                <Link
                  key={p.id}
                  href={`/app/projects/${p.id}`}
                  className="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-ip-card-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[14px] font-semibold text-ip-ink">{p.name}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      {p.time_bar_at_risk > 0 && (
                        <Chip tone="risk">{p.time_bar_at_risk} time-barred</Chip>
                      )}
                      {p.counts.pending > 0 && <Chip tone="navy">{p.counts.pending} pending</Chip>}
                      {!p.has_contract && <Chip tone="orange">No contract</Chip>}
                    </div>
                  </div>

                  <div className="shrink-0 text-right">
                    <div className="text-[14px] font-bold tabular-nums tracking-display text-ip-ink">
                      {aud(p.recoverable_confirmed)}
                    </div>
                    <div className="text-[11px] text-ip-ink-3">confirmed</div>
                  </div>

                  <ArrowRight className="h-4 w-4 shrink-0 text-ip-ink-3" aria-hidden />
                </Link>
              ))}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}

function Metric({ label, value, href }: { label: string; value: string; href?: string }) {
  const body = (
    <>
      <dt className="ip-label">{label}</dt>
      <dd className="mt-1.5 text-[22px] font-bold leading-none tabular-nums tracking-display text-ip-ink">
        {value}
      </dd>
    </>
  );
  const base = "px-5 py-4 border-ip-line [&:not(:first-child)]:border-l lg:[&:not(:first-child)]:border-l-0 lg:[&:not(:first-child)]:border-t";
  return href ? (
    <Link href={href} className={`${base} block transition-colors hover:bg-ip-card-2`}>
      {body}
    </Link>
  ) : (
    <div className={base}>{body}</div>
  );
}

/* Onboarding entry points belong in the empty state, not permanently parked on
   a dashboard someone opens every day. Once there is a project, these vanish. */
function FirstRun() {
  return (
    <div className="ip-card-lg p-8 sm:p-10">
      <h2 className="text-[20px] font-bold tracking-display text-ip-ink">
        Start recovering variations
      </h2>
      <p className="mt-2 max-w-lg text-[14px] leading-relaxed text-ip-ink-2">
        Upload your project record — RFIs, site instructions and meeting minutes — then run detection
        to surface variations that were never claimed.
      </p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Link href="/app/documents" className="btn-navy">
          <FileUp className="h-4 w-4" aria-hidden />
          Upload documents
        </Link>
        <Link href="/app/analysis" className="btn-ghost">
          <ScanSearch className="h-4 w-4" aria-hidden />
          Run analysis
        </Link>
      </div>
    </div>
  );
}
