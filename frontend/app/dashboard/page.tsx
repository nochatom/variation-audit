"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getCompanyId, getToken, logout, OrgDashboard } from "@/lib/api";

const aud = (n: number) => "$" + Math.round(n).toLocaleString();

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [state, setState] = useState("NSW");
  const [contract, setContract] = useState("");

  async function load() {
    const cid = getCompanyId();
    if (!cid) return;
    try {
      setData(await api.orgDashboard(cid));
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    load();
  }, [router]);

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    const cid = getCompanyId();
    if (!cid || !name) return;
    await api.createProject(cid, name, contract || undefined, state || undefined);
    setName("");
    setContract("");
    load();
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-hairline bg-canvas/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <div className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-sm bg-primary text-xs font-bold text-white">V</span>
            <span className="text-sm font-semibold tracking-tight">Variation Audit</span>
          </div>
          <button onClick={() => { logout(); router.replace("/login"); }}
            className="text-sm text-ink-subtle transition-colors hover:text-ink">Log out</button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8">
        <h1 className="mb-1 text-2xl font-semibold tracking-tightest">Dashboard</h1>
        <p className="mb-6 text-sm text-ink-subtle">Variation recovery across your projects.</p>

        {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

        {data && (
          <div className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat label="Projects" value={String(data.totals.projects)} />
            <Stat label="Pending review" value={String(data.totals.pending)} />
            <Stat label="Recoverable (confirmed)" value={aud(data.totals.recoverable_confirmed)} accent />
          </div>
        )}

        <div className="va-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-subtle">
                <th className="px-4 py-2.5 font-medium">Project</th>
                <th className="px-4 py-2.5 font-medium">Pending</th>
                <th className="px-4 py-2.5 font-medium">Confirmed</th>
                <th className="px-4 py-2.5 font-medium">Time-bar</th>
                <th className="px-4 py-2.5 font-medium">Recoverable</th>
              </tr>
            </thead>
            <tbody>
              {data?.projects.map((p) => (
                <tr key={p.id} className="border-b border-hairline last:border-0 transition-colors hover:bg-surface-2">
                  <td className="px-4 py-3">
                    <Link href={`/projects/${p.id}`} className="font-medium text-ink hover:text-primary-hover">
                      {p.name}
                    </Link>
                    {!p.has_contract && (
                      <span className="ml-2 rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-ink-subtle">no contract</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{p.counts.pending}</td>
                  <td className="px-4 py-3 text-ink-muted">{p.counts.confirmed}</td>
                  <td className="px-4 py-3">
                    {p.time_bar_at_risk > 0
                      ? <span className="text-amber-400">⚠ {p.time_bar_at_risk}</span>
                      : <span className="text-ink-tertiary">—</span>}
                  </td>
                  <td className="px-4 py-3 font-medium">{aud(p.recoverable_confirmed)}</td>
                </tr>
              ))}
              {data && data.projects.length === 0 && (
                <tr><td className="px-4 py-8 text-center text-ink-subtle" colSpan={5}>No projects yet — create one below.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <form onSubmit={createProject} className="va-panel mt-6 flex flex-wrap items-end gap-3 p-5">
          <div className="min-w-[200px] flex-1">
            <label className="va-eyebrow mb-1 block">Project name</label>
            <input className="va-input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="va-eyebrow mb-1 block">State</label>
            <input className="va-input w-24" value={state} onChange={(e) => setState(e.target.value)} />
          </div>
          <div className="w-full">
            <label className="va-eyebrow mb-1 block">Contract text (optional)</label>
            <textarea className="va-input" rows={2} value={contract} onChange={(e) => setContract(e.target.value)} />
          </div>
          <button className="va-btn-primary">Create project</button>
        </form>
      </main>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="va-panel p-4">
      <div className="va-eyebrow">{label}</div>
      <div className={`mt-1.5 text-2xl font-semibold tracking-tight ${accent ? "text-primary-hover" : ""}`}>{value}</div>
    </div>
  );
}
