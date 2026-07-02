"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ProjectDashboard, ProjectOut, VariationSummary } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, StatCard, Card, Chip, ConfidenceBar, TimeBarFlag, ErrorNote, InfoNote, Spinner, statusTone, aud } from "@/components/ui";
import { ProjectActionsMenu, DeleteProjectModal } from "@/components/project-actions";

export default function ProjectDetails() {
  const { companyId, isAdmin } = useApp();
  const router = useRouter();
  const projectId = useParams<{ id: string }>().id;

  const [dash, setDash] = useState<ProjectDashboard | null>(null);
  const [proj, setProj] = useState<ProjectOut | null>(null);
  const [pending, setPending] = useState<VariationSummary[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const load = useCallback(async () => {
    if (!companyId) return;
    const [d, p, q] = await Promise.all([
      api.projectDashboard(projectId),
      api.getProject(projectId),
      api.reviewQueue(projectId, companyId, "pending"),
    ]);
    setDash(d);
    setProj(p);
    setPending(q);
  }, [companyId, projectId]);

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);

  const archived = !!proj?.archived_at;

  async function archive() {
    setLifecycleBusy(true);
    try {
      await api.archiveProject(projectId);
      setMsg("Project archived — hidden from the dashboard, fully recoverable from Projects → Archived.");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function restore() {
    setLifecycleBusy(true);
    try {
      await api.unarchiveProject(projectId);
      setMsg("Project restored to the active dashboard.");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function confirmDelete() {
    setLifecycleBusy(true);
    try {
      await api.deleteProject(projectId);
      router.replace("/projects");
    } catch (e: any) {
      setError(e.message);
      setLifecycleBusy(false);
      setConfirmingDelete(false);
    }
  }

  async function analyze() {
    setMsg("Queuing analysis…");
    try {
      const r = await api.analyze(projectId);
      setMsg(`Analysis job ${r.job_id} (${r.status}). Refresh once it completes.`);
    } catch (e: any) {
      setMsg(e.message);
    }
  }
  async function downloadPdf() {
    try {
      const blob = await api.reportPdf(projectId);
      window.open(URL.createObjectURL(blob), "_blank");
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  return (
    <div>
      <div className="mb-2"><Link href="/projects" className="text-[13px] text-ip-ink-3 hover:text-ip-ink">← Projects</Link></div>
      <PageHeader
        title={dash?.project.name || "Project"}
        description={dash ? `${dash.project.state || "—"} · ${dash.project.status} · ${dash.document_count} documents` : undefined}
        actions={
          <>
            {archived && <Chip>archived</Chip>}
            <Link href={`/documents?project=${projectId}`} className="btn-ghost">Documents</Link>
            <button onClick={downloadPdf} className="btn-ghost">Report PDF</button>
            <button onClick={analyze} className="btn-orange">Run analysis</button>
            {proj && (
              <ProjectActionsMenu
                project={proj}
                isAdmin={isAdmin}
                busy={lifecycleBusy}
                onArchive={archive}
                onRestore={restore}
                onRequestDelete={() => setConfirmingDelete(true)}
              />
            )}
          </>
        }
      />

      {error && <ErrorNote message={error} />}
      {msg && <div className="mb-4"><InfoNote>{msg}</InfoNote></div>}
      {!dash && !error && <Spinner />}

      {dash && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Recoverable" value={aud(dash.recoverable_confirmed)} accent="recovery" hint="AUD confirmed" />
            <StatCard label="Pending" value={String(dash.counts.pending)} accent="navy" hint="awaiting review" />
            <StatCard label="Confirmed" value={String(dash.counts.confirmed)} hint="approved variations" />
            <StatCard label="Time-bar risk" value={String(dash.time_bar_at_risk)} accent={dash.time_bar_at_risk ? "risk" : "navy"} />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="overflow-hidden lg:col-span-2">
              <div className="flex items-center justify-between border-b border-ip-line px-4 py-3">
                <h2 className="text-sm font-bold text-ip-ink">Pending variations</h2>
                <Link href={`/variations?project=${projectId}`} className="text-[13px] text-ip-ink-3 hover:text-ip-ink">Open in Variations →</Link>
              </div>
              {pending.length === 0 ? (
                <div className="px-4 py-10 text-center text-[13px] text-ip-ink-3">No pending variations. Run analysis to detect more.</div>
              ) : (
                <table className="w-full">
                  <thead><tr className="border-b border-ip-line"><th className="ip-th">Variation</th><th className="ip-th">Confidence</th><th className="ip-th">Time-bar</th><th className="ip-th text-right">Value</th></tr></thead>
                  <tbody>
                    {pending.slice(0, 8).map((v) => (
                      <tr key={v.id} className="ip-row">
                        <td className="px-4 py-3 text-sm font-semibold text-ip-ink"><Link href={`/variations/${v.id}`} className="hover:text-ip-navy">{v.title}</Link></td>
                        <td className="px-4 py-3"><ConfidenceBar score={v.confidence_score} /></td>
                        <td className="px-4 py-3 text-sm"><TimeBarFlag risk={v.time_bar_risk} /></td>
                        <td className="px-4 py-3 text-right text-sm font-bold tabular-nums text-ip-ink">{aud(v.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            <div className="space-y-6">
              <Card className="p-5">
                <h3 className="text-sm font-bold text-ip-ink">Readiness</h3>
                <div className="mt-3 space-y-2 text-sm">
                  <Row k="Contract baseline" v={dash.project.has_contract ? <Chip tone="recovery">present</Chip> : <Chip tone="orange">missing</Chip>} />
                  <Row k="Documents" v={<span className="font-semibold tabular-nums">{dash.document_count}</span>} />
                  <Row k="State / SoP" v={dash.project.state || "—"} />
                </div>
              </Card>
              <Card className="p-5">
                <h3 className="text-sm font-bold text-ip-ink">Latest analysis</h3>
                {dash.latest_job ? (
                  <div className="mt-3 space-y-2 text-sm">
                    <Row k="Status" v={<Chip tone={statusTone(dash.latest_job.status)}>{dash.latest_job.status}</Chip>} />
                    <Row k="Recoverable total" v={<span className="font-bold tabular-nums text-ip-recovery">{aud(dash.latest_job.recoverable_total)}</span>} />
                  </div>
                ) : (
                  <p className="mt-3 text-[13px] text-ip-ink-2">No analysis yet. Add documents, then run analysis.</p>
                )}
              </Card>
            </div>
          </div>

          {confirmingDelete && dash && (
            <DeleteProjectModal
              projectName={dash.project.name}
              busy={lifecycleBusy}
              onCancel={() => setConfirmingDelete(false)}
              onConfirm={confirmDelete}
            />
          )}
        </>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-ip-line py-2 last:border-0">
      <span className="text-ip-ink-2">{k}</span>
      <span>{v}</span>
    </div>
  );
}
