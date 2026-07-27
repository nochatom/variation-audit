"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowDown, Check, Undo2, X } from "lucide-react";
import { api, VariationSummary } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ConfidenceBar, TimeBarFlag, ErrorNote, Spinner, EmptyState, aud } from "@/components/ui";

const TABS = ["pending", "confirmed", "rejected"] as const;
type Tab = (typeof TABS)[number];
type Row = VariationSummary & { projectId: string; projectName: string };

const BANDS = ["all", "high", "medium", "low"] as const;
type Band = (typeof BANDS)[number];

type Sort = "value" | "confidence";

/** A reversal target for the last decision — commercial sign-off needs a way back. */
type LastAction = { row: Row; from: Tab; to: Tab };

export default function VariationsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <VariationsInner />
    </Suspense>
  );
}

function VariationsInner() {
  const { companyId } = useApp();
  const projectFilter = useSearchParams().get("project");
  const [tab, setTab] = useState<Tab>("pending");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [band, setBand] = useState<Band>("all");
  const [minValue, setMinValue] = useState("");
  const [sort, setSort] = useState<Sort>("value");
  const [last, setLast] = useState<LastAction | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!companyId) return;
    setRows(null);
    const dash = await api.orgDashboard(companyId);
    const projects = projectFilter ? dash.projects.filter((p) => p.id === projectFilter) : dash.projects;
    const lists = await Promise.all(
      projects.map((p) =>
        api
          .reviewQueue(p.id, companyId, tab)
          .then((q) => q.map((v) => ({ ...v, projectId: p.id, projectName: p.name })))
          .catch(() => [] as Row[]),
      ),
    );
    setRows(lists.flat());
  }, [companyId, tab, projectFilter]);

  useEffect(() => {
    setLast(null);
    load().catch((e) => setError(e.message));
  }, [load]);

  /** Optimistic: the row leaves the current tab immediately, and the decision
   *  stays reversible until the next one. Approving six figures shouldn't
   *  need a modal, but it must not be a one-way click either. */
  async function act(row: Row, to: Tab) {
    setBusyId(row.id);
    setRows((rs) => (rs ?? []).filter((r) => r.id !== row.id));
    try {
      await api.review(row.id, to);
      setLast({ row, from: tab, to });
    } catch (e: any) {
      setError(e.message);
      setRows((rs) => [...(rs ?? []), row]);
    } finally {
      setBusyId(null);
    }
  }

  async function undo() {
    if (!last) return;
    setBusyId(last.row.id);
    try {
      await api.review(last.row.id, last.from);
      setRows((rs) => [...(rs ?? []), last.row]);
      setLast(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  const visible = useMemo(() => {
    const floor = Number(minValue.replace(/[^0-9.]/g, "")) || 0;
    return (rows ?? [])
      .filter((r) => band === "all" || (r.confidence_band ?? "").toLowerCase() === band)
      .filter((r) => (r.amount ?? 0) >= floor)
      .sort((a, b) => {
        // Time bars outrank everything: value you cannot claim isn't value.
        if (a.time_bar_risk !== b.time_bar_risk) return a.time_bar_risk ? -1 : 1;
        if (sort === "confidence") return b.confidence_score - a.confidence_score;
        return (b.amount ?? 0) - (a.amount ?? 0);
      });
  }, [rows, band, minValue, sort]);

  const total = visible.reduce((s, r) => s + (r.amount ?? 0), 0);
  const atRisk = visible.filter((r) => r.time_bar_risk).length;
  const filtered = (rows?.length ?? 0) - visible.length;

  // Green is the recovered-money token — it must not label rejected value.
  const totalTone =
    tab === "confirmed" ? "text-ip-recovery" : tab === "rejected" ? "text-ip-ink-3" : "text-ip-ink";

  return (
    <div>
      <PageHeader
        title="AI findings"
        description="Every variation the engine detected, ranked by what it's worth and how long you have to claim it."
      />
      {error && <ErrorNote message={error} />}

      {/* ---- Protagonist: the value under review in this filter. One figure,
           sized so nothing else competes, honest about which tab it sums. ---- */}
      <div className="ip-card-lg mb-4 flex flex-wrap items-end justify-between gap-4 p-6">
        <div>
          <h2 className="ip-label">
            {tab === "pending" ? "Awaiting a decision" : tab === "confirmed" ? "Approved value" : "Rejected value"}
          </h2>
          <div className={`mt-3 text-[40px] font-bold leading-none tabular-nums tracking-display sm:text-[52px] ${totalTone}`}>
            {aud(total)}
          </div>
          <p className="mt-2 text-[13px] text-ip-ink-2">
            {visible.length} {visible.length === 1 ? "finding" : "findings"}
            {filtered > 0 && ` · ${filtered} hidden by filters`}
          </p>
        </div>

        {atRisk > 0 && tab === "pending" && (
          <div className="rounded-md border border-ip-risk/30 bg-ip-risk-bg px-3.5 py-2.5">
            <div className="text-[13px] font-bold text-ip-risk">
              {atRisk} {atRisk === 1 ? "finding is" : "findings are"} time-barred
            </div>
            <div className="mt-0.5 text-[12px] text-ip-ink-2">Sorted to the top of the queue.</div>
          </div>
        )}
      </div>

      {/* ---- Triage controls. Confidence band was fetched and discarded before;
           it is the axis a reviewer actually filters on. ---- */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex w-fit gap-1 rounded-md border border-ip-line bg-ip-card p-1" role="tablist" aria-label="Review status">
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`rounded-xs px-3.5 py-1.5 text-sm font-semibold capitalize transition-colors ${
                tab === t ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="flex w-fit gap-1 rounded-md border border-ip-line bg-ip-card p-1" role="group" aria-label="Confidence band">
          {BANDS.map((b) => (
            <button
              key={b}
              aria-pressed={band === b}
              onClick={() => setBand(b)}
              className={`rounded-xs px-2.5 py-1.5 text-[13px] font-semibold capitalize transition-colors ${
                band === b ? "bg-ip-card-3 text-ip-ink" : "text-ip-ink-3 hover:text-ip-ink"
              }`}
            >
              {b}
            </button>
          ))}
        </div>

        <div>
          <label htmlFor="min-value" className="sr-only">Minimum value</label>
          <input
            id="min-value"
            className="ip-input w-36"
            value={minValue}
            onChange={(e) => setMinValue(e.target.value)}
            placeholder="Min value"
            inputMode="numeric"
          />
        </div>

        <button
          onClick={() => setSort((s) => (s === "value" ? "confidence" : "value"))}
          className="btn-ghost"
          aria-label={`Sorting by ${sort}. Switch to ${sort === "value" ? "confidence" : "value"}.`}
        >
          <ArrowDown className="h-3.5 w-3.5" aria-hidden />
          {sort === "value" ? "Value" : "Confidence"}
        </button>
      </div>

      {last && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-ip-line bg-ip-card-2 px-4 py-2.5">
          <Check className="h-4 w-4 shrink-0 text-ip-recovery" aria-hidden />
          <span className="flex-1 text-[13px] text-ip-ink-2">
            <span className="font-semibold text-ip-ink">{last.row.title}</span> marked {last.to}.
          </span>
          <button onClick={undo} disabled={busyId === last.row.id} className="btn-ghost">
            <Undo2 className="h-3.5 w-3.5" aria-hidden />
            Undo
          </button>
        </div>
      )}

      {!rows && !error && <Spinner />}

      {rows && rows.length === 0 && (
        <EmptyState
          title={`No ${tab} findings`}
          body="When analysis detects variations, they appear here for review."
        />
      )}

      {rows && rows.length > 0 && visible.length === 0 && (
        <EmptyState
          title="No findings match these filters"
          body="Lower the minimum value or widen the confidence band."
          action={
            <button onClick={() => { setBand("all"); setMinValue(""); }} className="btn-ghost">
              Clear filters
            </button>
          }
        />
      )}

      {visible.length > 0 && (
        <Card className="divide-y divide-ip-line">
          {visible.map((v) => (
            <FindingRow key={v.id} row={v} tab={tab} busy={busyId === v.id} onAct={act} />
          ))}
        </Card>
      )}
    </div>
  );
}

/**
 * One finding. Value is the largest element in the row because value is the
 * decision; title, project, confidence and time-bar are the evidence for it.
 */
function FindingRow({
  row,
  tab,
  busy,
  onAct,
}: {
  row: Row;
  tab: Tab;
  busy: boolean;
  onAct: (row: Row, to: Tab) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 px-4 py-4 transition-colors hover:bg-ip-card-2">
      <div className="min-w-[220px] flex-1">
        <Link
          href={`/app/variations/${row.id}`}
          className="text-[15px] font-semibold leading-snug text-ip-ink hover:text-ip-navy"
        >
          {row.title}
        </Link>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px]">
          <Link href={`/app/projects/${row.projectId}`} className="text-ip-ink-3 hover:text-ip-navy">
            {row.projectName}
          </Link>
          {/* The bar already encodes the score — only a low band earns a second
              mark, because it changes how hard the reviewer should look. */}
          {row.confidence_band === "low" && <Chip tone="orange">low confidence</Chip>}
          {row.time_bar_risk && <TimeBarFlag risk />}
        </div>
      </div>

      <div className="shrink-0">
        <ConfidenceBar score={row.confidence_score} />
      </div>

      <div className="shrink-0 text-right">
        <div className="text-[20px] font-bold leading-none tabular-nums tracking-display text-ip-ink">
          {aud(row.amount)}
        </div>
        <div className="mt-1 text-[11px] text-ip-ink-3">recoverable</div>
      </div>

      <div className="flex shrink-0 gap-2">
        {tab !== "confirmed" && (
          <button
            onClick={() => onAct(row, "confirmed")}
            disabled={busy}
            aria-label={`Approve ${row.title}`}
            className="inline-flex items-center gap-1 rounded-md bg-ip-recovery/12 px-2.5 py-1.5 text-xs font-semibold text-ip-recovery transition-colors hover:bg-ip-recovery/20 disabled:opacity-50"
          >
            <Check className="h-3.5 w-3.5" aria-hidden />
            Approve
          </button>
        )}
        {tab !== "rejected" && (
          <button
            onClick={() => onAct(row, "rejected")}
            disabled={busy}
            aria-label={`Reject ${row.title}`}
            className="inline-flex items-center gap-1 rounded-md bg-ip-risk/10 px-2.5 py-1.5 text-xs font-semibold text-ip-risk transition-colors hover:bg-ip-risk/20 disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
            Reject
          </button>
        )}
        {tab !== "pending" && (
          <button
            onClick={() => onAct(row, "pending")}
            disabled={busy}
            aria-label={`Reopen ${row.title}`}
            className="rounded-md border border-ip-line-strong px-2.5 py-1.5 text-xs font-semibold text-ip-ink-2 transition-colors hover:bg-ip-card-2 disabled:opacity-50"
          >
            Reopen
          </button>
        )}
      </div>
    </div>
  );
}
