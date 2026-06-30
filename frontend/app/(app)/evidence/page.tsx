"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, EvidenceContext, VariationSummary } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState, aud, fmtDate } from "@/components/ui";

type Item = VariationSummary & { projectName: string };

export default function EvidenceLibraryPage() {
  const { companyId } = useApp();
  const [items, setItems] = useState<Item[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceContext[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!companyId) return;
    const dash = await api.orgDashboard(companyId);
    const lists = await Promise.all(
      dash.projects.flatMap((p) =>
        (["confirmed", "pending"] as const).map((s) =>
          api.reviewQueue(p.id, companyId, s)
            .then((q) => q.map((v) => ({ ...v, projectName: p.name })))
            .catch(() => [] as Item[]),
        ),
      ),
    );
    const flat = lists.flat();
    setItems(flat);
    if (flat.length && !selected) setSelected(flat[0].id);
  }, [companyId, selected]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  useEffect(() => {
    if (!selected) return;
    setEvidence(null);
    api.variationEvidence(selected).then(setEvidence).catch((e) => setError(e.message));
  }, [selected]);

  const current = items?.find((i) => i.id === selected) ?? null;

  return (
    <div>
      <PageHeader title="Evidence Library" description="Trace any variation back to the source documents it was detected from." />
      {error && <ErrorNote message={error} />}
      {!items && !error && <Spinner />}

      {items && items.length === 0 && <EmptyState title="No variations to trace" body="Run analysis to detect variations, then explore their evidence here." />}

      {items && items.length > 0 && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          {/* list */}
          <Card className="h-fit overflow-hidden">
            <div className="border-b border-ip-line px-4 py-3"><h2 className="text-sm font-bold text-ip-ink">Variations ({items.length})</h2></div>
            <ul className="max-h-[60vh] divide-y divide-ip-line overflow-y-auto">
              {items.map((v) => (
                <li key={v.id}>
                  <button onClick={() => setSelected(v.id)} className={`block w-full px-4 py-3 text-left transition-colors ${selected === v.id ? "bg-ip-card-2" : "hover:bg-ip-card-2"}`}>
                    <div className="truncate text-[13px] font-semibold text-ip-ink">{v.title}</div>
                    <div className="mt-0.5 flex items-center justify-between text-[12px] text-ip-ink-3">
                      <span className="truncate">{v.projectName}</span>
                      <span className="font-semibold tabular-nums text-ip-recovery">{aud(v.amount)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {/* evidence pane */}
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-ip-line px-5 py-3">
              <div>
                <h2 className="text-sm font-bold text-ip-ink">{current?.title ?? "Evidence"}</h2>
                {current && <div className="text-[12px] text-ip-ink-3">{current.projectName}</div>}
              </div>
              {current && <Link href={`/variations/${current.id}`} className="text-[13px] text-ip-ink-3 hover:text-ip-ink">Open variation →</Link>}
            </div>

            {!evidence ? (
              <Spinner />
            ) : evidence.length === 0 ? (
              <div className="px-5 py-12 text-center text-[13px] text-ip-ink-3">No linked evidence for this variation.</div>
            ) : (
              <ul className="divide-y divide-ip-line">
                {evidence.map((e, i) => (
                  <li key={i} className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Chip tone="navy">{e.type}</Chip>
                      {e.reference && <span className="text-[12px] font-semibold text-ip-ink">{e.reference}</span>}
                      {e.source_document && (
                        <span className="text-[12px] text-ip-ink-3">· {e.source_document.source_type}{e.source_document.source ? ` · ${e.source_document.source}` : ""}{e.source_document.doc_timestamp ? ` · ${fmtDate(e.source_document.doc_timestamp)}` : ""}</span>
                      )}
                    </div>
                    {e.quote && <blockquote className="mt-2 border-l-2 border-ip-line-strong pl-3 text-[13px] italic leading-relaxed text-ip-ink-2">“{e.quote}”</blockquote>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
