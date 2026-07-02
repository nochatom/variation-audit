"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ProjectDashboard, ProjectOut, VariationSummary } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, StatCard, Card, Chip, ConfidenceBar, TimeBarFlag, ErrorNote, InfoNote, Spinner, statusTone, aud } from "@/components/ui";

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

  async function toggleArchive() {
    setLifecycleBusy(true);
    try {
      if (archived) {
        await api.unarchiveProject(projectId);
        setMsg("Project restored to the active dashboard.");
      } else {
        await api.archiveProject(projectId);
        setMsg("Project archived — hidden from the dashboard, fully recoverable from Projects → Archived.");
      }
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
            <button onClick={toggleArchive} disabled={lifecycleBusy} className="btn-ghost">
              {lifecycleBusy ? "…" : archived ? "Restore" : "Archive"}
            </button>
            <Link href={`/documents?project=${projectId}`} className="btn-ghost">Documents</Link>
            <button onClick={downloadPdf} className="btn-ghost">Report PDF</button>
            <button onClick={analyze} className="btn-orange">Run analysis</button>
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

          {isAdmin && (
            <Card className="mt-6 border-ip-risk/30 p-5">
              <h3 className="text-sm font-bold text-ip-risk">Danger zone</h3>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <p className="text-[13px] text-ip-ink-2">
                  Permanently delete this project and <span className="font-semibold">all</span> of its
                  documents, analyses, variations, evidence and comments. This cannot be undone —
                  prefer <span className="font-semibold">Archive</span> unless you are certain.
                </p>
                <button onClick={() => setConfirmingDelete(true)}
                        className="rounded-md bg-ip-risk/10 px-3.5 py-2 text-sm font-semibold text-ip-risk hover:bg-ip-risk/20">
                  Delete project…
                </button>
              </div>
            </Card>
          )}

          {confirmingDelete && dash && (
            <DeleteModal
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

function DeleteModal({ projectName, busy, onCancel, onConfirm }: {
  projectName: string; busy: boolean; onCancel: () => void; onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const match = typed.trim() === projectName;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ip-navy/40 px-4" onClick={onCancel}>
      <div className="ip-card-lg w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-ip-risk">Permanently delete project?</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-ip-ink-2">
          This deletes <span className="font-semibold text-ip-ink">{projectName}</span> and every
          document, analysis job, variation, evidence record and comment in it.{" "}
          <span className="font-semibold text-ip-risk">This action cannot be undone.</span>
        </p>
        <label className="ip-label mb-1 mt-4 block">Type the project name to confirm</label>
        <input className="ip-input" value={typed} onChange={(e) => setTyped(e.target.value)}
               placeholder={projectName} autoFocus />
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="btn-ghost" disabled={busy}>Cancel</button>
          <button onClick={onConfirm} disabled={!match || busy}
                  className="rounded-md bg-ip-risk px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:opacity-90 disabled:opacity-40">
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
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
