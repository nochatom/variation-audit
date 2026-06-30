"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ProjectDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, InfoNote, ErrorNote, Spinner, EmptyState, statusTone, aud } from "@/components/ui";

export default function AnalysisPage() {
  const { companyId } = useApp();
  const [rows, setRows] = useState<ProjectDashboard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!companyId) return;
    const dash = await api.orgDashboard(companyId);
    const details = await Promise.all(dash.projects.map((p) => api.projectDashboard(p.id).catch(() => null)));
    setRows(details.filter((d): d is ProjectDashboard => d !== null));
  }, [companyId]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  async function run(projectId: string, name: string) {
    setRunning(projectId);
    setMsg(null);
    try {
      const r = await api.analyze(projectId);
      setMsg(`Analysis queued for ${name} — job ${r.job_id} (${r.status}). Results appear once it completes.`);
      await load();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setRunning(null);
    }
  }

  return (
    <div>
      <PageHeader title="Analysis" description="Run AI detection on a project's record and track each analysis job." />
      {error && <ErrorNote message={error} />}
      {msg && <div className="mb-4"><InfoNote>{msg}</InfoNote></div>}
      {!rows && !error && <Spinner />}

      {rows && rows.length === 0 && <EmptyState title="No projects to analyze" body="Create a project and ingest documents first." />}

      {rows && rows.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ip-line">
                <th className="ip-th">Project</th>
                <th className="ip-th">Documents</th>
                <th className="ip-th">Last job</th>
                <th className="ip-th">Recoverable (job)</th>
                <th className="ip-th text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.project.id} className="ip-row">
                  <td className="px-4 py-3 text-sm font-semibold text-ip-ink">
                    <Link href={`/projects/${d.project.id}`} className="hover:text-ip-navy">{d.project.name}</Link>
                  </td>
                  <td className="px-4 py-3 text-sm tabular-nums text-ip-ink-2">{d.document_count}</td>
                  <td className="px-4 py-3 text-sm">{d.latest_job ? <Chip tone={statusTone(d.latest_job.status)}>{d.latest_job.status}</Chip> : <span className="text-ip-ink-3">never run</span>}</td>
                  <td className="px-4 py-3 text-sm font-bold tabular-nums text-ip-recovery">{d.latest_job ? aud(d.latest_job.recoverable_total) : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => run(d.project.id, d.project.name)} disabled={running === d.project.id} className="btn-orange">
                      {running === d.project.id ? "Queuing…" : "Run analysis"}
                    </button>
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
