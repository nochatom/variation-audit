"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, ErrorNote, Spinner, EmptyState } from "@/components/ui";

const UPLOADS = [
  { kind: "rfis", label: "RFI register", hint: "CSV — rfi_number, subject, question, response, dates, status" },
  { kind: "site-instructions", label: "Site instructions", hint: "CSV — si_number, date_issued, issued_by, instruction" },
  { kind: "meeting-minutes", label: "Meeting minutes", hint: "CSV — item, date, topic, decision, action, owner" },
  { kind: "comms", label: "Project comms", hint: "CSV — general communications register" },
] as const;

export default function DocumentsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <DocumentsInner />
    </Suspense>
  );
}

function DocumentsInner() {
  const { companyId } = useApp();
  const preselect = useSearchParams().get("project");
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [projectId, setProjectId] = useState<string>("");
  const [docCount, setDocCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    api.orgDashboard(companyId).then((d) => {
      setData(d);
      const initial = preselect && d.projects.some((p) => p.id === preselect) ? preselect : d.projects[0]?.id ?? "";
      setProjectId(initial);
    }).catch((e) => setError(e.message));
  }, [companyId, preselect]);

  function refreshCount(id: string) {
    if (!id) return;
    api.projectDashboard(id).then((d) => setDocCount(d.document_count)).catch(() => setDocCount(null));
  }
  useEffect(() => { refreshCount(projectId); }, [projectId]);

  return (
    <div>
      <PageHeader title="Documents" description="Ingest the project record. Each source becomes evidence the engine reasons over." />
      {error && <ErrorNote message={error} />}
      {!data && !error && <Spinner />}

      {data && data.projects.length === 0 && <EmptyState title="No projects yet" body="Create a project first, then ingest its documents here." />}

      {data && data.projects.length > 0 && (
        <>
          <Card className="mb-6 flex flex-wrap items-end justify-between gap-4 p-5">
            <div className="min-w-[240px] flex-1">
              <label className="ip-label mb-1 block">Project</label>
              <select className="ip-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {data.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div className="text-sm text-ip-ink-2">
              Documents ingested: <span className="font-bold tabular-nums text-ip-ink">{docCount ?? "—"}</span>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <UploadCard
              label="Contract / scope baseline"
              hint="PDF or text — the agreed scope the engine compares against."
              accept=".pdf,.txt"
              onUpload={(f) => api.uploadContract(projectId, f).then(() => "Contract baseline updated.")}
              onDone={() => refreshCount(projectId)}
            />
            {UPLOADS.map((u) => (
              <UploadCard
                key={u.kind}
                label={u.label}
                hint={u.hint}
                accept=".csv"
                onUpload={(f) => api.uploadDocs(projectId, u.kind, f).then((r) => `${r.documents_added} document(s) ingested.`)}
                onDone={() => refreshCount(projectId)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function UploadCard({ label, hint, accept, onUpload, onDone }: {
  label: string; hint: string; accept: string; onUpload: (f: File) => Promise<string>; onDone: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handle(file?: File) {
    if (!file) return;
    setBusy(true);
    setStatus(null);
    try {
      setStatus(await onUpload(file));
      onDone();
    } catch (e: any) {
      setStatus(e.message);
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <Card className="flex flex-col p-5">
      <h3 className="text-sm font-bold text-ip-ink">{label}</h3>
      <p className="mt-1 flex-1 text-[12px] leading-relaxed text-ip-ink-2">{hint}</p>
      <input ref={ref} type="file" accept={accept} className="hidden" onChange={(e) => handle(e.target.files?.[0])} />
      <div className="mt-3 flex items-center gap-3">
        <button onClick={() => ref.current?.click()} disabled={busy} className="btn-ghost">{busy ? "Uploading…" : "Choose file"}</button>
        {status && <span className="text-[12px] text-ip-ink-2">{status}</span>}
      </div>
    </Card>
  );
}
