"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, VariationSummary } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, ConfidenceBar, TimeBarFlag, ErrorNote, Spinner, EmptyState, aud } from "@/components/ui";

const TABS = ["pending", "confirmed", "rejected"] as const;
type Row = VariationSummary & { projectId: string; projectName: string };

export default function VariationsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <VariationsInner />
    </Suspense>
  );
}

function VariationsInner() {
  const { companyId } = useApp();
  const projectFilter = useSearchParams().get("project");
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!companyId) return;
    setRows(null);
    const dash = await api.orgDashboard(companyId);
    const projects = projectFilter ? dash.projects.filter((p) => p.id === projectFilter) : dash.projects;
    const lists = await Promise.all(
      projects.map((p) =>
        api.reviewQueue(p.id, companyId, tab)
          .then((q) => q.map((v) => ({ ...v, projectId: p.id, projectName: p.name })))
          .catch(() => [] as Row[]),
      ),
    );
    setRows(lists.flat());
  }, [companyId, tab, projectFilter]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  async function act(id: string, status: "confirmed" | "rejected" | "pending") {
    await api.review(id, status);
    load();
  }

  const total = rows?.reduce((s, r) => s + (r.amount ?? 0), 0) ?? 0;

  return (
    <div>
      <PageHeader title="Variations" description="Every detected variation across your projects, in one decision surface." />
      {error && <ErrorNote message={error} />}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-md border border-ip-line bg-ip-card p-1">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`rounded-sm px-3.5 py-1.5 text-sm font-semibold capitalize transition-colors ${tab === t ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"}`}>{t}</button>
          ))}
        </div>
        {rows && rows.length > 0 && (
          <div className="text-sm text-ip-ink-2">{rows.length} {tab} · <span className="font-bold tabular-nums text-ip-recovery">{aud(total)}</span> est. value</div>
        )}
      </div>

      {!rows && !error && <Spinner />}
      {rows && rows.length === 0 && <EmptyState title={`No ${tab} variations`} body="When analysis detects variations, they appear here for review." />}

      {rows && rows.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ip-line">
                <th className="ip-th">Variation</th>
                <th className="ip-th">Project</th>
                <th className="ip-th">Confidence</th>
                <th className="ip-th">Time-bar</th>
                <th className="ip-th">Value</th>
                <th className="ip-th text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.id} className="ip-row hover:bg-ip-card-2">
                  <td className="px-4 py-3 text-sm font-semibold text-ip-ink"><Link href={`/variations/${v.id}`} className="hover:text-ip-navy">{v.title}</Link></td>
                  <td className="px-4 py-3 text-sm"><Link href={`/projects/${v.projectId}`} className="text-ip-ink-2 hover:text-ip-navy">{v.projectName}</Link></td>
                  <td className="px-4 py-3"><ConfidenceBar score={v.confidence_score} /></td>
                  <td className="px-4 py-3 text-sm"><TimeBarFlag risk={v.time_bar_risk} /></td>
                  <td className="px-4 py-3 text-sm font-bold tabular-nums text-ip-ink">{aud(v.amount)}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      {tab !== "confirmed" && <button onClick={() => act(v.id, "confirmed")} className="rounded-md bg-ip-recovery/12 px-2.5 py-1 text-xs font-semibold text-ip-recovery hover:bg-ip-recovery/20">Approve</button>}
                      {tab !== "rejected" && <button onClick={() => act(v.id, "rejected")} className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk hover:bg-ip-risk/20">Reject</button>}
                      {tab !== "pending" && <button onClick={() => act(v.id, "pending")} className="rounded-md border border-ip-line-strong px-2.5 py-1 text-xs font-semibold text-ip-ink-2 hover:bg-ip-card-2">Reopen</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
