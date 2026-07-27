"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, ChevronDown, FileText, TriangleAlert, Upload } from "lucide-react";
import { api, OrgDashboard } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState } from "@/components/ui";

const REGISTERS = [
  { kind: "rfis", label: "RFI register", hint: "rfi_number · subject · question · response · dates · status" },
  { kind: "site-instructions", label: "Site instructions", hint: "si_number · date_issued · issued_by · instruction" },
  { kind: "meeting-minutes", label: "Meeting minutes", hint: "item · date · topic · decision · action · owner" },
  { kind: "comms", label: "Project comms", hint: "general communications register" },
] as const;

/** Result of an ingest in this session. The API exposes no document history,
 *  so this is the only record the user gets — it must not be a transient string. */
type Receipt = { ok: boolean; message: string; at: number };

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
  const [hasContract, setHasContract] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId) return;
    api
      .orgDashboard(companyId)
      .then((d) => {
        setData(d);
        const initial =
          preselect && d.projects.some((p) => p.id === preselect) ? preselect : d.projects[0]?.id ?? "";
        setProjectId(initial);
      })
      .catch((e) => setError(e.message));
  }, [companyId, preselect]);

  const refresh = useCallback((id: string) => {
    if (!id) return;
    api
      .projectDashboard(id)
      .then((d) => {
        setDocCount(d.document_count);
        setHasContract(d.project.has_contract);
      })
      .catch(() => {
        setDocCount(null);
        setHasContract(null);
      });
  }, []);

  useEffect(() => {
    refresh(projectId);
  }, [projectId, refresh]);

  const project = data?.projects.find((p) => p.id === projectId);

  return (
    <div>
      <PageHeader
        title="Documents"
        description="Ingest the project record. Each source becomes evidence the engine reasons over."
        actions={
          projectId ? (
            <Link href={`/app/analysis?project=${projectId}`} className="btn-ghost">
              Run analysis
            </Link>
          ) : undefined
        }
      />

      {error && <ErrorNote message={error} />}
      {!data && !error && <Spinner />}

      {data && data.projects.length === 0 && (
        <EmptyState
          title="No projects yet"
          body="Create a project first, then ingest its documents here."
          action={<Link href="/app/projects" className="btn-orange">Create project</Link>}
        />
      )}

      {data && data.projects.length > 0 && (
        <>
          {/* Toolbar, not a panel — choosing the project is navigation, not content. */}
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div className="relative">
              <label htmlFor="doc-project" className="sr-only">Project</label>
              <select
                id="doc-project"
                className="ip-input w-full appearance-none pr-8 font-semibold sm:w-72"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
              >
                {data.projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ip-ink-3"
                aria-hidden
              />
            </div>
            <div className="text-[13px] text-ip-ink-2">
              <span className="font-bold tabular-nums text-ip-ink">{docCount ?? "—"}</span> documents
              ingested
            </div>
          </div>

          {/* ---- Protagonist: the scope baseline. Detection has nothing to
               compare against without it, so its absence dominates the page
               and its presence shrinks to a single confirmed line. ---- */}
          <Baseline
            key={`baseline-${projectId}`}
            projectId={projectId}
            hasContract={hasContract ?? project?.has_contract ?? false}
            onDone={() => refresh(projectId)}
          />

          <h2 className="ip-label mb-3 mt-8">Registers</h2>
          <Card className="divide-y divide-ip-line">
            {REGISTERS.map((r) => (
              <IngestRow
                key={`${projectId}-${r.kind}`}
                label={r.label}
                hint={r.hint}
                format="CSV"
                accept=".csv"
                onUpload={(f) =>
                  api.uploadDocs(projectId, r.kind, f).then((res) => `${res.documents_added} rows ingested`)
                }
                onDone={() => refresh(projectId)}
              />
            ))}
            <IngestRow
              key={`${projectId}-doc`}
              label="Supporting document"
              hint="A single drawing, letter or report to keep on the record"
              format="PDF · TXT"
              accept=".pdf,.txt"
              onUpload={(f) => api.uploadDocument(projectId, f).then(() => "Document stored")}
              onDone={() => refresh(projectId)}
            />
          </Card>
        </>
      )}
    </div>
  );
}

/** Contract baseline — the one upload that gates everything downstream. */
function Baseline({
  projectId,
  hasContract,
  onDone,
}: {
  projectId: string;
  hasContract: boolean;
  onDone: () => void;
}) {
  const [receipt, setReceipt] = useState<Receipt | null>(null);

  const handle = (f: File) =>
    api.uploadContract(projectId, f).then(() => "Baseline updated");

  if (hasContract && !receipt?.ok) {
    // Settled state: confirmed in one line. A large panel for a solved
    // problem is exactly the kind of weight this page can't afford.
    return (
      <div className="ip-card flex flex-wrap items-center gap-3 px-4 py-3">
        <Check className="h-4 w-4 shrink-0 text-ip-recovery" aria-hidden />
        <span className="flex-1 text-[13px] font-semibold text-ip-ink">
          Scope baseline in place
        </span>
        <DropButton
          label="Replace"
          accept=".pdf,.txt"
          onUpload={handle}
          onResult={(r) => {
            setReceipt(r);
            if (r.ok) onDone();
          }}
          ghost
        />
      </div>
    );
  }

  return (
    <DropZone
      accept=".pdf,.txt"
      onUpload={handle}
      onResult={(r) => {
        setReceipt(r);
        if (r.ok) onDone();
      }}
      receipt={receipt}
    />
  );
}

function DropZone({
  accept,
  onUpload,
  onResult,
  receipt,
}: {
  accept: string;
  onUpload: (f: File) => Promise<string>;
  onResult: (r: Receipt) => void;
  receipt: Receipt | null;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handle(file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      onResult({ ok: true, message: await onUpload(file), at: Date.now() });
    } catch (e: any) {
      onResult({ ok: false, message: e.message, at: Date.now() });
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        handle(e.dataTransfer.files?.[0]);
      }}
      className={`ip-card-lg border-dashed px-6 py-10 text-center transition-colors ${
        over ? "border-ip-orange bg-ip-card-2" : "border-ip-line-strong"
      }`}
    >
      <TriangleAlert className="mx-auto h-6 w-6 text-ip-orange-2" aria-hidden />
      <h2 className="mt-3 text-[20px] font-bold tracking-display text-ip-ink">
        No scope baseline yet
      </h2>
      <p className="mx-auto mt-2 max-w-md text-[14px] leading-relaxed text-ip-ink-2">
        The engine detects variations by comparing the project record against the agreed scope.
        Until a baseline exists, detection has nothing to measure against.
      </p>

      <input
        ref={ref}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => handle(e.target.files?.[0])}
      />
      <button onClick={() => ref.current?.click()} disabled={busy} className="btn-orange mx-auto mt-5">
        <Upload className="h-4 w-4" aria-hidden />
        {busy ? "Uploading…" : "Upload baseline"}
      </button>
      <p className="mt-2 text-[12px] text-ip-ink-3">or drop a PDF or text file here</p>

      {receipt && !receipt.ok && (
        <p className="mx-auto mt-4 max-w-md rounded-md border border-ip-risk/30 bg-ip-risk-bg px-3 py-2 text-[13px] font-medium text-ip-risk">
          {receipt.message}
        </p>
      )}
    </div>
  );
}

/** One register source: label, expected format, drop target, persistent receipt. */
function IngestRow({
  label,
  hint,
  format,
  accept,
  onUpload,
  onDone,
}: {
  label: string;
  hint: string;
  format: string;
  accept: string;
  onUpload: (f: File) => Promise<string>;
  onDone: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handle(file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      setReceipt({ ok: true, message: await onUpload(file), at: Date.now() });
      onDone();
    } catch (e: any) {
      setReceipt({ ok: false, message: e.message, at: Date.now() });
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        handle(e.dataTransfer.files?.[0]);
      }}
      className={`flex flex-wrap items-center gap-3 px-4 py-3.5 transition-colors ${
        over ? "bg-ip-card-2" : ""
      }`}
    >
      <FileText className="h-4 w-4 shrink-0 text-ip-ink-3" aria-hidden />

      <div className="min-w-[180px] flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold text-ip-ink">{label}</span>
          <Chip>{format}</Chip>
        </div>
        <div className="mt-0.5 truncate text-[12px] text-ip-ink-3">{hint}</div>
      </div>

      {/* Receipts persist for the session — the API offers no ingest history,
          so a vanishing toast would leave no evidence anything happened. */}
      {receipt && (
        <span
          className={`text-[12px] font-semibold ${receipt.ok ? "text-ip-recovery" : "text-ip-risk"}`}
          role="status"
        >
          {receipt.ok ? <Check className="mr-1 inline h-3.5 w-3.5" aria-hidden /> : null}
          {receipt.message}
        </span>
      )}

      <input
        ref={ref}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => handle(e.target.files?.[0])}
      />
      <button onClick={() => ref.current?.click()} disabled={busy} className="btn-ghost shrink-0">
        {busy ? "Uploading…" : "Choose file"}
      </button>
    </div>
  );
}

function DropButton({
  label,
  accept,
  onUpload,
  onResult,
  ghost,
}: {
  label: string;
  accept: string;
  onUpload: (f: File) => Promise<string>;
  onResult: (r: Receipt) => void;
  ghost?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function handle(file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      onResult({ ok: true, message: await onUpload(file), at: Date.now() });
    } catch (e: any) {
      onResult({ ok: false, message: e.message, at: Date.now() });
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => handle(e.target.files?.[0])}
      />
      <button
        onClick={() => ref.current?.click()}
        disabled={busy}
        className={ghost ? "btn-ghost shrink-0" : "btn-navy shrink-0"}
      >
        {busy ? "Uploading…" : label}
      </button>
    </>
  );
}
