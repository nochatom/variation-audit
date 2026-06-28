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
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <button onClick={() => { logout(); router.replace("/login"); }}
          className="text-sm text-slate-500 hover:underline">Log out</button>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {data && (
        <div className="mb-6 grid grid-cols-3 gap-4">
          <Stat label="Projects" value={String(data.totals.projects)} />
          <Stat label="Pending review" value={String(data.totals.pending)} />
          <Stat label="Recoverable (confirmed)" value={aud(data.totals.recoverable_confirmed)} />
        </div>
      )}

      <div className="overflow-hidden rounded-xl border bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">Project</th>
              <th className="px-4 py-2">Pending</th>
              <th className="px-4 py-2">Confirmed</th>
              <th className="px-4 py-2">Time-bar</th>
              <th className="px-4 py-2">Recoverable</th>
            </tr>
          </thead>
          <tbody>
            {data?.projects.map((p) => (
              <tr key={p.id} className="border-t hover:bg-slate-50">
                <td className="px-4 py-2">
                  <Link href={`/projects/${p.id}`} className="font-medium text-blue-700 hover:underline">
                    {p.name}
                  </Link>
                  {!p.has_contract && <span className="ml-2 text-xs text-amber-600">no contract</span>}
                </td>
                <td className="px-4 py-2">{p.counts.pending}</td>
                <td className="px-4 py-2">{p.counts.confirmed}</td>
                <td className="px-4 py-2">{p.time_bar_at_risk > 0 ? `⚠ ${p.time_bar_at_risk}` : "—"}</td>
                <td className="px-4 py-2">{aud(p.recoverable_confirmed)}</td>
              </tr>
            ))}
            {data && data.projects.length === 0 && (
              <tr><td className="px-4 py-6 text-slate-400" colSpan={5}>No projects yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <form onSubmit={createProject} className="mt-6 flex flex-wrap items-end gap-2 rounded-xl border bg-white p-4 shadow-sm">
        <div className="flex-1">
          <label className="block text-xs text-slate-500">Project name</label>
          <input className="w-full rounded border px-3 py-2" value={name}
            onChange={(e) => setName(e.target.value)} required />
        </div>
        <div>
          <label className="block text-xs text-slate-500">State</label>
          <input className="w-24 rounded border px-3 py-2" value={state}
            onChange={(e) => setState(e.target.value)} />
        </div>
        <div className="w-full">
          <label className="block text-xs text-slate-500">Contract text (optional)</label>
          <textarea className="w-full rounded border px-3 py-2" rows={2} value={contract}
            onChange={(e) => setContract(e.target.value)} />
        </div>
        <button className="rounded bg-slate-900 px-4 py-2 text-white">Create project</button>
      </form>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}
