"use client";

import { useEffect, useState } from "react";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState, statusTone, aud } from "@/components/ui";

export default function ReportsPage() {
  const { companyId } = useApp();
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    api.orgDashboard(companyId).then(setData).catch((e) => setError(e.message));
  }, [companyId]);

  async function download(projectId: string) {
    setBusy(projectId);
    try {
      const blob = await api.reportPdf(projectId);
      window.open(URL.createObjectURL(blob), "_blank");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <PageHeader title="Reports" description="Generate a review-ready variation-recovery report for any project." />
      {error && <ErrorNote message={error} />}
      {!data && !error && <Spinner />}
      {data && data.projects.length === 0 && <EmptyState title="No projects to report on" body="Create a project and run analysis to generate a report." />}

      {data && data.projects.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ip-line">
                <th className="ip-th">Project</th>
                <th className="ip-th">Status</th>
                <th className="ip-th">Confirmed</th>
                <th className="ip-th">Recoverable</th>
                <th className="ip-th text-right">Report</th>
              </tr>
            </thead>
            <tbody>
              {data.projects.map((p) => (
                <tr key={p.id} className="ip-row hover:bg-ip-card-2">
                  <td className="px-4 py-3 text-sm font-semibold text-ip-ink">{p.name}</td>
                  <td className="px-4 py-3 text-sm"><Chip tone={statusTone(p.status)}>{p.status}</Chip></td>
                  <td className="px-4 py-3 text-sm tabular-nums text-ip-ink-2">{p.counts.confirmed}</td>
                  <td className="px-4 py-3 text-sm font-bold tabular-nums text-ip-recovery">{aud(p.recoverable_confirmed)}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => download(p.id)} disabled={busy === p.id} className="btn-ghost">{busy === p.id ? "Generating…" : "Download PDF"}</button>
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
