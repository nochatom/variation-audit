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
const TABS: Array<VariationSummary["review_status"]> = ["pending", "confirmed", "rejected"];

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
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <Link href="/dashboard" className="text-sm text-blue-700 hover:underline">← Dashboard</Link>

      <div className="mt-2 mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{dash?.project.name || "Project"}</h1>
          <p className="text-sm text-slate-500">
            {dash?.project.state || "—"} · status {dash?.project.status} ·{" "}
            {dash?.document_count ?? 0} documents
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={analyze} className="rounded bg-slate-900 px-3 py-2 text-sm text-white">
            Run analysis
          </button>
          <button onClick={downloadPdf} className="rounded border px-3 py-2 text-sm">
            Report PDF
          </button>
        </div>
      </div>

      {msg && <p className="mb-4 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">{msg}</p>}

      {dash && (
        <div className="mb-6 grid grid-cols-4 gap-4">
          <Stat label="Confirmed" value={String(dash.counts.confirmed)} />
          <Stat label="Pending" value={String(dash.counts.pending)} />
          <Stat label="Recoverable" value={aud(dash.recoverable_confirmed)} />
          <Stat label="Time-bar risk" value={String(dash.time_bar_at_risk)} />
        </div>
      )}

      <div className="mb-3 flex gap-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded px-3 py-1 text-sm capitalize ${tab === t ? "bg-slate-900 text-white" : "bg-slate-100"}`}>
            {t}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">Variation</th>
              <th className="px-4 py-2">Confidence</th>
              <th className="px-4 py-2">Time-bar</th>
              <th className="px-4 py-2">Est. value</th>
              <th className="px-4 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {queue.map((v) => (
              <tr key={v.id} className="border-t">
                <td className="px-4 py-2 font-medium">{v.title}</td>
                <td className="px-4 py-2">
                  {v.confidence_band} ({v.confidence_score.toFixed(2)})
                </td>
                <td className="px-4 py-2">{v.time_bar_risk ? "⚠ yes" : "no"}</td>
                <td className="px-4 py-2">{aud(v.amount)}</td>
                <td className="px-4 py-2">
                  {tab !== "confirmed" && (
                    <button onClick={() => act(v.id, "confirmed")}
                      className="mr-2 rounded bg-emerald-600 px-2 py-1 text-xs text-white">Approve</button>
                  )}
                  {tab !== "rejected" && (
                    <button onClick={() => act(v.id, "rejected")}
                      className="mr-2 rounded bg-red-600 px-2 py-1 text-xs text-white">Reject</button>
                  )}
                  {tab !== "pending" && (
                    <button onClick={() => act(v.id, "pending")}
                      className="rounded border px-2 py-1 text-xs">Reopen</button>
                  )}
                </td>
              </tr>
            ))}
            {queue.length === 0 && (
              <tr><td className="px-4 py-6 text-slate-400" colSpan={5}>No {tab} variations.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}
