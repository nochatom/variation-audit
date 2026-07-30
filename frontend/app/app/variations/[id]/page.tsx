"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { api, VariationDetail, EvidenceContext, AuditEntry } from "@/lib/api";
import { ConfidenceBar, TimeBarFlag, ErrorNote, Spinner, aud, fmtDate } from "@/components/ui";
import {
  BasisQuality,
  Claim,
  ClaimNote,
  EvidenceSpine,
  Fact,
  Money,
  RailSection,
  STATUS_LABEL,
  Section,
  TimeBarNotice,
  fmtDay,
  spineMeta,
} from "@/components/app/recover";

export default function VariationDetailsPage() {
  const id = useParams<{ id: string }>().id;
  const [v, setV] = useState<VariationDetail | null>(null);
  const [evidence, setEvidence] = useState<EvidenceContext[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [detail, ev, au] = await Promise.all([
      api.variation(id),
      api.variationEvidence(id).catch(() => []),
      api.variationAudit(id).catch(() => []),
    ]);
    setV(detail);
    setEvidence(ev);
    setAudit(au);
  }, [id]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  async function review(status: "confirmed" | "rejected" | "pending") {
    await api.review(id, status);
    load();
  }
  async function addComment(e: React.FormEvent) {
    e.preventDefault();
    if (!comment.trim()) return;
    setBusy(true);
    try {
      await api.addComment(id, comment.trim());
      setComment("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const status = v?.review_status ?? "pending";

  return (
    <div>
      <div className="mb-5">
        <Link
          href="/app/variations"
          className="inline-flex items-center gap-1.5 rounded-sm text-[13px] font-medium text-ip-ink-3 transition-colors hover:text-ip-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ip-navy/40 focus-visible:ring-offset-2 focus-visible:ring-offset-ip-bg"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          Variations
        </Link>
      </div>

      {error && <ErrorNote message={error} />}
      {!v && !error && <Spinner />}

      {v && (
        <>
          {/* ── The case ──────────────────────────────────────────────────
              A finding is an assertion the reviewer has to judge, so the page
              opens by stating the assertion in prose rather than dealing the
              same facts out across a row of metric tiles. */}
          <header className="mb-8 border-b border-ip-line pb-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="ip-label">Detected variation</span>
                  <span className="text-ip-line-strong" aria-hidden>·</span>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ip-ink-2">
                    {STATUS_LABEL[status] ?? status}
                  </span>
                </div>
                {/* Deliberately smaller than the claim below it. The title
                    names the finding; the claim *is* the finding, and two
                    30px blocks stacked would have them compete. */}
                <h1 className="mt-1.5 max-w-2xl text-[21px] font-semibold leading-[1.25] tracking-display text-ip-ink">
                  {v.title}
                </h1>
              </div>

              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {status !== "confirmed" && <button onClick={() => review("confirmed")} className="btn-orange">Approve</button>}
                {status !== "rejected" && <button onClick={() => review("rejected")} className="btn-ghost">Reject</button>}
                {status !== "pending" && <button onClick={() => review("pending")} className="btn-ghost">Reopen</button>}
              </div>
            </div>

            <div className="mt-6">
              <FindingClaim value={v.value} amount={v.amount} />
            </div>

            {v.time_bar_risk && (
              <div className="mt-6">
                <TimeBarNotice>
                  <span className="font-semibold">The notice window may have closed.</span>{" "}
                  <span className="text-ip-ink-2">
                    Check the contract&rsquo;s notice clause against the earliest evidence date below before you claim this.
                  </span>
                </TimeBarNotice>
              </div>
            )}
          </header>

          <div className="grid grid-cols-1 gap-x-10 gap-y-10 lg:grid-cols-[minmax(0,1fr)_300px]">
            {/* ── The argument ──────────────────────────────────────────── */}
            <div className="min-w-0">
              <Section title="Why this was flagged">
                <p className="max-w-[68ch] whitespace-pre-wrap text-[15px] leading-[1.7] text-ip-ink-2">
                  {v.description || "The analysis recorded no reasoning for this finding."}
                </p>
              </Section>

              <Section title="Evidence" meta={evidence.length > 0 ? spineMeta(evidence) : undefined}>
                <EvidenceSpine
                  items={evidence}
                  empty={
                    <p className="max-w-[68ch] text-[14px] leading-relaxed text-ip-ink-3">
                      Nothing in the ingested documents was linked to this finding. Without a source
                      quote there is no basis to claim it — reject it, or upload the correspondence it
                      should have come from and run the analysis again.
                    </p>
                  }
                />
              </Section>

              <Section title="Review notes">
                <div className="max-w-[68ch] space-y-3">
                  {v.comments.length === 0 && (
                    <p className="text-[14px] text-ip-ink-3">
                      No one has commented yet. Record why you approved or rejected this — the note
                      travels with the claim.
                    </p>
                  )}
                  {v.comments.map((c) => (
                    <div key={c.id} className="rounded-md border border-ip-line bg-ip-card-2 px-3.5 py-3">
                      <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ip-ink">{c.body}</p>
                      <div className="mt-1.5 text-[11px] tabular-nums text-ip-ink-3">{fmtDate(c.created_at)}</div>
                    </div>
                  ))}

                  <form onSubmit={addComment} className="pt-1">
                    <label htmlFor="review-note" className="sr-only">Review note</label>
                    <textarea
                      id="review-note"
                      className="ip-input min-h-[76px] resize-y leading-relaxed"
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      maxLength={5000}
                      placeholder="Add a review note…"
                    />
                    <div className="mt-2 flex justify-end">
                      <button className="btn-navy" disabled={busy || !comment.trim()}>
                        {busy ? "Posting…" : "Post note"}
                      </button>
                    </div>
                  </form>
                </div>
              </Section>
            </div>

            {/* ── The reading ───────────────────────────────────────────────
                A rail, not a stack of cards: these are qualifiers on the claim
                above, and cards would give each one the same weight as the
                claim itself. */}
            {/* order-first on small screens: confidence and basis change how
                hard the reviewer should read the evidence, so they belong
                before it, not stacked underneath at the bottom of a scroll.
                top-[76px] clears the 56px sticky topbar plus 20px. */}
            <aside className="order-first space-y-8 lg:order-none lg:sticky lg:top-[76px] lg:self-start">
              <RailSection title="Assessment">
                <Fact k="Confidence" v={<ConfidenceBar score={v.confidence_score} />} />
                <Fact k="Band" v={<span className="text-[13px] font-medium capitalize text-ip-ink">{v.confidence_band ?? "—"}</span>} />
                <Fact k="Basis" v={<BasisQuality quality={v.value?.basis_quality} />} />
                <Fact k="Time-bar" v={<span className="text-[13px]"><TimeBarFlag risk={v.time_bar_risk} /></span>} />
              </RailSection>

              <RailSection title="Estimate">
                <Fact k="Low" v={<Money n={v.value?.estimate_low} />} />
                <Fact k="Likely" v={<Money n={v.value?.amount ?? v.amount} strong />} />
                <Fact k="High" v={<Money n={v.value?.estimate_high} />} />
              </RailSection>

              <RailSection title="History">
                {audit.length === 0 ? (
                  <p className="py-2 text-[13px] text-ip-ink-3">Nothing recorded yet.</p>
                ) : (
                  <ol className="space-y-2.5 pt-1">
                    {audit.map((a) => (
                      <li key={a.id} className="flex items-baseline justify-between gap-3">
                        {/* Sentence case, not title case: `capitalize` would
                            render "Opened For Review". */}
                        <span className="text-[13px] font-medium first-letter:uppercase text-ip-ink">
                          {a.action.replace(/_/g, " ")}
                        </span>
                        <span className="shrink-0 text-[11px] tabular-nums text-ip-ink-3">{fmtDay(a.created_at) ?? "—"}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </RailSection>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The finding, stated. Money leads because money is the decision, but the
 * shared Claim register keeps the hedge welded to it. Local to this page
 * because the sentence is about one variation; the queue states a position
 * across many, so it writes its own.
 */
function FindingClaim({ value, amount }: { value: VariationDetail["value"]; amount: number | null }) {
  const likely = value?.amount ?? amount;
  const low = value?.estimate_low;
  const high = value?.estimate_high;

  if (likely == null) {
    return (
      <Claim>
        Work outside the contract scope appears to have been carried out,{" "}
        <span className="text-ip-ink-3">but the analysis could not put a value on it.</span>
      </Claim>
    );
  }

  return (
    <Claim>
      <span className="tabular-nums text-ip-recovery">{aud(likely)}</span> of work appears to have
      been carried out and never claimed.
      {low != null && high != null && (
        <ClaimNote>
          Estimated between <span className="tabular-nums text-ip-ink-2">{aud(low)}</span> and{" "}
          <span className="tabular-nums text-ip-ink-2">{aud(high)}</span>.
        </ClaimNote>
      )}
    </Claim>
  );
}
