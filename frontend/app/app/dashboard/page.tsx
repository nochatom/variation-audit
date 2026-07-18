"use client";

import { useEffect, useState, ReactNode } from "react";
import Link from "next/link";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, StatCard, Card, ErrorNote, Spinner, aud } from "@/components/ui";

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
  const attention = data?.projects.filter((p) => p.time_bar_at_risk > 0 || p.counts.pending > 0) ?? [];

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Recovery position across the organization. Jump into a workflow to act."
        actions={<Link href="/app/projects" className="btn-orange">New project</Link>}
      />

      {error && <ErrorNote message={error} />}
      {!data && !error && <Spinner />}

      {data && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Recoverable (confirmed)" value={aud(t!.recoverable_confirmed)} accent="recovery" hint="AUD approved" />
            <StatCard label="Pending review" value={String(t!.pending)} accent="navy" hint="awaiting a decision" />
            <StatCard label="Time-bar at risk" value={String(atRisk)} accent={atRisk ? "risk" : "navy"} hint="contractual deadlines" />
            <StatCard label="Active projects" value={String(t!.projects)} hint="in your organization" />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <h2 className="ip-label mb-3">Workflows</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <NavCard href="/app/variations" title="Review variations" body="Approve or reject detected variations across projects." meta={`${t!.pending} pending`} />
                <NavCard href="/app/documents" title="Ingest documents" body="Upload RFIs, site instructions and meeting minutes." meta="RFI · SI · Minutes" />
                <NavCard href="/app/analysis" title="Run analysis" body="Detect unclaimed variations from the project record." meta="AI detection" />
                <NavCard href="/app/reports" title="Generate reports" body="Export a review-ready recovery report per project." meta="PDF export" />
              </div>
            </div>

            <div>
              <h2 className="ip-label mb-3">Needs attention</h2>
              <Card className="divide-y divide-ip-line">
                {attention.length === 0 && <div className="px-4 py-8 text-center text-[13px] text-ip-ink-3">Nothing needs attention.</div>}
                {attention.slice(0, 6).map((p) => (
                  <Link key={p.id} href={`/app/projects/${p.id}`} className="flex items-center justify-between px-4 py-3 hover:bg-ip-card-2">
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-semibold text-ip-ink">{p.name}</div>
                      <div className="text-[12px] text-ip-ink-3">{p.counts.pending} pending</div>
                    </div>
                    {p.time_bar_at_risk > 0 && <span className="shrink-0 text-[12px] font-semibold text-ip-risk">⚠ {p.time_bar_at_risk}</span>}
                  </Link>
                ))}
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function NavCard({ href, title, body, meta }: { href: string; title: string; body: string; meta: ReactNode }) {
  return (
    <Link href={href} className="ip-card ip-card-interactive group p-5 hover:bg-ip-card-2">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-bold tracking-tight text-ip-ink">{title}</h3>
        <span className="text-ip-ink-3 transition-transform duration-150 ease-out group-hover:translate-x-0.5">→</span>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ip-ink-2">{body}</p>
      <div className="ip-label mt-3 text-ip-ink-3">{meta}</div>
    </Link>
  );
}
