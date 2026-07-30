"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { api, EvidenceContext, VariationSummary } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { Chip, ErrorNote, Spinner, EmptyState, TimeBarFlag, aud } from "@/components/ui";
import { EvidenceSpine, STATUS_LABEL, Section, spineMeta } from "@/components/app/recover";

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
      <header className="mb-8 border-b border-ip-line pb-8">
        <span className="ip-label">Evidence library</span>
        <h1 className="mt-1.5 max-w-2xl text-[21px] font-semibold leading-[1.25] tracking-display text-ip-ink">
          Trace any variation back to the correspondence it was detected from
        </h1>
        <p className="mt-3 max-w-[68ch] text-[14px] leading-relaxed text-ip-ink-2">
          Every finding is only as good as its paper trail. Pick a variation to read its sources in
          the order they were written.
        </p>
      </header>

      {error && <ErrorNote message={error} />}
      {!items && !error && <Spinner />}

      {items && items.length === 0 && (
        <EmptyState
          title="No variations to trace"
          body="Run analysis to detect variations, then read their evidence here."
        />
      )}

      {items && items.length > 0 && (
        <div className="grid grid-cols-1 gap-x-10 gap-y-10 lg:grid-cols-[280px_minmax(0,1fr)]">
          {/* ---- Picker. A rail of names, not a panel of cards: choosing which
               variation to read is navigation, and navigation shouldn't
               out-weigh the evidence it leads to. ---- */}
          <nav className="order-first lg:order-none lg:sticky lg:top-[76px] lg:self-start" aria-label="Variations">
            <h2 className="ip-label mb-3 border-b border-ip-line pb-2">
              Variations ({items.length})
            </h2>
            <ul className="max-h-[62vh] overflow-y-auto">
              {items.map((v) => {
                const active = selected === v.id;
                return (
                  <li key={v.id}>
                    <button
                      onClick={() => setSelected(v.id)}
                      aria-current={active ? "true" : undefined}
                      className={`group block w-full border-l-2 py-2.5 pl-3 pr-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ip-navy/40 ${
                        active
                          ? "border-l-ip-navy bg-ip-card-2"
                          : "border-l-transparent hover:border-l-ip-line-strong hover:bg-ip-card-2"
                      }`}
                    >
                      <span
                        className={`block text-[13px] font-semibold leading-snug ${
                          active ? "text-ip-ink" : "text-ip-ink-2 group-hover:text-ip-ink"
                        }`}
                      >
                        {v.title}
                      </span>
                      <span className="mt-1 flex items-center justify-between gap-2 text-[11px] text-ip-ink-3">
                        <span className="truncate">{v.projectName}</span>
                        {v.amount != null && (
                          <span className="shrink-0 font-semibold tabular-nums">{aud(v.amount)}</span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>

          {/* ---- The evidence itself, on the same spine the variation detail
               page uses — one component, so a reviewer reads the same proof
               the same way whichever door they came in through. ---- */}
          <div className="min-w-0">
            {current && (
              <div className="mb-8">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="ip-label">{current.projectName}</span>
                  <span className="text-ip-line-strong" aria-hidden>·</span>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ip-ink-2">
                    {STATUS_LABEL[current.review_status] ?? current.review_status}
                  </span>
                  {current.time_bar_risk && (
                    <span className="text-[12px]"><TimeBarFlag risk /></span>
                  )}
                </div>
                <h2 className="mt-1.5 max-w-3xl text-[19px] font-semibold leading-[1.3] tracking-display text-ip-ink">
                  {current.title}
                </h2>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  {current.amount != null && (
                    <Chip tone="recovery">{aud(current.amount)} recoverable</Chip>
                  )}
                  <Link
                    href={`/app/variations/${current.id}`}
                    className="inline-flex items-center gap-1.5 rounded-sm text-[13px] font-semibold text-ip-navy hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ip-navy/40 focus-visible:ring-offset-2 focus-visible:ring-offset-ip-bg"
                  >
                    Open variation to decide
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                </div>
              </div>
            )}

            {!evidence ? (
              <Spinner />
            ) : (
              <Section title="Evidence" meta={evidence.length > 0 ? spineMeta(evidence) : undefined}>
                <EvidenceSpine
                  items={evidence}
                  empty={
                    <p className="max-w-[68ch] text-[14px] leading-relaxed text-ip-ink-3">
                      No sources are linked to this variation, so there is nothing to trace. Upload
                      the correspondence it should have come from and run the analysis again.
                    </p>
                  }
                />
              </Section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
