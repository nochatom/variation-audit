"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  api,
  getCompanyId,
  getToken,
  ProjectDashboard,
  VariationSummary,
} from "@/lib/api";

const aud = (n: number | null) => (n == null ? "—" : "$" + Math.round(n).toLocaleString());
const TABS = ["pending", "confirmed", "rejected"];

const BAND: Record<string, string> = {
  high: "text-success",
  medium: "text-amber-400",
  low: "text-ink-subtle",
};

export default function ProjectPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [dash, setDash] = useState<ProjectDashboard | null>(null);
  const [tab, setTab] = useState("pending");
  const [queue, setQueue] = useState<VariationSummary[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const cid = getCompanyId();
    if (!cid) return;
    const [d, q] = await Promise.all([
      api.projectDashboard(projectId),
      api.reviewQueue(projectId, cid, tab),
    ]);
    setDash(d);
    setQueue(q);
  }, [projectId, tab]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    load().catch((e) => setMsg(e.message));
  }, [load, router]);

  async function act(id: string, status: "confirmed" | "rejected" | "pending") {
    await api.review(id, status);
    load();
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
    const blob = await api.reportPdf(projectId);
    window.open(URL.createObjectURL(blob), "_blank");
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-hairline bg-canvas/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <Link href="/dashboard" className="text-sm text-ink-subtle transition-colors hover:text-ink">← Dashboard</Link>
          <div className="flex gap-2">
            <button onClick={analyze} className="va-btn-primary">Run analysis</button>
            <button onClick={downloadPdf} className="va-btn-secondary">Report PDF</button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">
        <h1 className="text-2xl font-semibold tracking-tightest">{dash?.project.name || "Project"}</h1>
        <p className="mt-1 text-sm text-ink-subtle">
          {dash?.project.state || "—"} · {dash?.project.status} · {dash?.document_count ?? 0} documents
        </p>

        {msg && (
          <p className="mt-4 rounded-md border border-hairline bg-surface-2 px-3 py-2 text-sm text-ink-muted">{msg}</p>
        )}

        {dash && (
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Confirmed" value={String(dash.counts.confirmed)} />
            <Stat label="Pending" value={String(dash.counts.pending)} />
            <Stat label="Recoverable" value={aud(dash.recoverable_confirmed)} accent />
            <Stat label="Time-bar risk" value={String(dash.time_bar_at_risk)} />
          </div>
        )}

        <div className="mb-3 mt-7 flex gap-1 rounded-md bg-canvas p-1">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded-sm px-3 py-1.5 text-sm font-medium capitalize transition-colors ${
                tab === t ? "bg-surface-2 text-ink" : "text-ink-subtle hover:text-ink"
              }`}>
              {t}
            </button>
          ))}
        </div>

        <div className="va-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-subtle">
                <th className="px-4 py-2.5 font-medium">Variation</th>
                <th className="px-4 py-2.5 font-medium">Confidence</th>
                <th className="px-4 py-2.5 font-medium">Time-bar</th>
                <th className="px-4 py-2.5 font-medium">Est. value</th>
                <th className="px-4 py-2.5 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((v) => (
                <tr key={v.id} className="border-b border-hairline last:border-0">
                  <td className="px-4 py-3 font-medium">{v.title}</td>
                  <td className="px-4 py-3">
                    <span className={BAND[v.confidence_band ?? "low"] ?? "text-ink-muted"}>
                      {v.confidence_band} ({v.confidence_score.toFixed(2)})
                    </span>
                  </td>
                  <td className="px-4 py-3">{v.time_bar_risk ? <span className="text-amber-400">⚠ yes</span> : <span className="text-ink-tertiary">no</span>}</td>
                  <td className="px-4 py-3 font-medium">{aud(v.amount)}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      {tab !== "confirmed" && (
                        <button onClick={() => act(v.id, "confirmed")}
                          className="rounded-sm bg-success/15 px-2 py-1 text-xs font-medium text-success hover:bg-success/25">Approve</button>
                      )}
                      {tab !== "rejected" && (
                        <button onClick={() => act(v.id, "rejected")}
                          className="rounded-sm bg-red-500/10 px-2 py-1 text-xs font-medium text-red-400 hover:bg-red-500/20">Reject</button>
                      )}
                      {tab !== "pending" && (
                        <button onClick={() => act(v.id, "pending")}
                          className="rounded-sm border border-hairline px-2 py-1 text-xs text-ink-muted hover:bg-surface-2">Reopen</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {queue.length === 0 && (
                <tr><td className="px-4 py-8 text-center text-ink-subtle" colSpan={5}>No {tab} variations.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="va-panel p-4">
      <div className="va-eyebrow">{label}</div>
      <div className={`mt-1.5 text-xl font-semibold tracking-tight ${accent ? "text-primary-hover" : ""}`}>{value}</div>
    </div>
  );
}
