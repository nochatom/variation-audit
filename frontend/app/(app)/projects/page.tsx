"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState, statusTone, aud } from "@/components/ui";

const AU_STATES = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"] as const;

export default function ProjectsPage() {
  const { companyId } = useApp();
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [name, setName] = useState("");
  const [state, setState] = useState("NSW");
  const [contract, setContract] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!companyId) return;
    try {
      setData(await api.orgDashboard(companyId));
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!companyId || !trimmedName) return;
    setBusy(true);
    try {
      await api.createProject(companyId, trimmedName, contract || undefined, state || undefined);
      setName("");
      setContract("");
      setCreating(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        description="Each project is a workspace for documents, analysis, and its review queue."
        actions={<button onClick={() => setCreating((v) => !v)} className="btn-orange">{creating ? "Cancel" : "New project"}</button>}
      />

      {error && <ErrorNote message={error} />}

      {creating && (
        <Card className="mb-6 p-5">
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="ip-label mb-1 block">Project name</label>
              <input className="ip-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sydney Metro — Package 4" minLength={1} maxLength={300} required />
            </div>
            <div>
              <label className="ip-label mb-1 block">State</label>
              <div className="relative">
                <select
                  className="ip-input w-28 appearance-none pr-7"
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                  required
                >
                  {AU_STATES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-ip-ink-3">▼</span>
              </div>
            </div>
            <div className="w-full">
              <label className="ip-label mb-1 block">Contract / scope text (optional)</label>
              <textarea className="ip-input" rows={3} value={contract} onChange={(e) => setContract(e.target.value)} maxLength={500000} placeholder="Paste the agreed scope baseline, or upload a document later from Documents." />
            </div>
            <button className="btn-navy" disabled={busy}>{busy ? "Creating…" : "Create project"}</button>
          </form>
        </Card>
      )}

      {!data && !error && <Spinner />}

      {data && data.projects.length === 0 && !creating && (
        <EmptyState title="No projects yet" body="Create a project to start ingesting documents and detecting unclaimed variations." action={<button onClick={() => setCreating(true)} className="btn-orange">Create project</button>} />
      )}

      {data && data.projects.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.projects.map((p) => (
            <Link key={p.id} href={`/projects/${p.id}`} className="ip-card group p-5 transition-colors hover:bg-ip-card-2">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-bold tracking-tight text-ip-ink">{p.name}</h3>
                <Chip tone={statusTone(p.status)}>{p.status}</Chip>
              </div>
              <div className="mt-1 flex items-center gap-2 text-[12px]">
                {!p.has_contract && <Chip tone="orange">no contract</Chip>}
                {p.time_bar_at_risk > 0 && <span className="font-semibold text-ip-risk">⚠ {p.time_bar_at_risk} time-bar</span>}
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 border-t border-ip-line pt-4 text-center">
                <Mini label="Pending" value={String(p.counts.pending)} />
                <Mini label="Confirmed" value={String(p.counts.confirmed)} />
                <Mini label="Recoverable" value={aud(p.recoverable_confirmed)} recovery />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Mini({ label, value, recovery }: { label: string; value: string; recovery?: boolean }) {
  return (
    <div>
      <div className={`text-sm font-bold tabular-nums ${recovery ? "text-ip-recovery" : "text-ip-ink"}`}>{value}</div>
      <div className="ip-label mt-0.5 text-ip-ink-3">{label}</div>
    </div>
  );
}
