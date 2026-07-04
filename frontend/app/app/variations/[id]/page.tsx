"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, VariationDetail, EvidenceContext, AuditEntry } from "@/lib/api";
import { PageHeader, Card, Chip, ConfidenceBar, TimeBarFlag, ErrorNote, Spinner, statusTone, aud, fmtDate } from "@/components/ui";

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
      <div className="mb-2"><Link href="/app/variations" className="text-[13px] text-ip-ink-3 hover:text-ip-ink">← Variations</Link></div>
      {error && <ErrorNote message={error} />}
      {!v && !error && <Spinner />}

      {v && (
        <>
          <PageHeader
            title={v.title}
            actions={
              <>
                {status !== "confirmed" && <button onClick={() => review("confirmed")} className="btn-orange">Approve</button>}
                {status !== "rejected" && <button onClick={() => review("rejected")} className="btn-ghost">Reject</button>}
                {status !== "pending" && <button onClick={() => review("pending")} className="btn-ghost">Reopen</button>}
              </>
            }
          />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* main column */}
            <div className="space-y-6 lg:col-span-2">
              <Card className="p-5">
                <h2 className="text-sm font-bold text-ip-ink">Description</h2>
                <p className="mt-2 whitespace-pre-wrap text-[14px] leading-relaxed text-ip-ink-2">{v.description || "No description provided."}</p>
              </Card>

              <Card className="overflow-hidden">
                <div className="border-b border-ip-line px-5 py-3"><h2 className="text-sm font-bold text-ip-ink">Evidence ({evidence.length})</h2></div>
                {evidence.length === 0 ? (
                  <div className="px-5 py-8 text-center text-[13px] text-ip-ink-3">No linked evidence.</div>
                ) : (
                  <ul className="divide-y divide-ip-line">
                    {evidence.map((e, i) => (
                      <li key={i} className="px-5 py-4">
                        <div className="flex items-center gap-2">
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

              <Card className="p-5">
                <h2 className="text-sm font-bold text-ip-ink">Comments</h2>
                <div className="mt-3 space-y-3">
                  {v.comments.length === 0 && <p className="text-[13px] text-ip-ink-3">No comments yet.</p>}
                  {v.comments.map((c) => (
                    <div key={c.id} className="rounded-md border border-ip-line bg-ip-card-2 px-3 py-2">
                      <div className="text-[14px] text-ip-ink">{c.body}</div>
                      <div className="mt-1 text-[11px] text-ip-ink-3">{fmtDate(c.created_at)}</div>
                    </div>
                  ))}
                </div>
                <form onSubmit={addComment} className="mt-4 flex gap-2">
                  <input className="ip-input" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={5000} placeholder="Add a review note…" />
                  <button className="btn-navy" disabled={busy}>{busy ? "Posting…" : "Post"}</button>
                </form>
              </Card>
            </div>

            {/* side column */}
            <div className="space-y-6">
              <Card className="p-5">
                <h3 className="text-sm font-bold text-ip-ink">Assessment</h3>
                <div className="mt-3 space-y-3 text-sm">
                  <Row k="Status" v={<Chip tone={statusTone(status)}>{status}</Chip>} />
                  <Row k="Confidence" v={<ConfidenceBar score={v.confidence_score} />} />
                  <Row k="Band" v={<span className="capitalize text-ip-ink">{v.confidence_band ?? "—"}</span>} />
                  <Row k="Time-bar" v={<TimeBarFlag risk={v.time_bar_risk} />} />
                </div>
              </Card>

              <Card className="p-5">
                <h3 className="text-sm font-bold text-ip-ink">Recoverable value</h3>
                <div className="mt-2 text-[28px] font-bold tabular-nums text-ip-recovery">{aud(v.value?.amount ?? v.amount)}</div>
                <div className="mt-1 text-[12px] text-ip-ink-3">
                  Range {aud(v.value?.estimate_low)} – {aud(v.value?.estimate_high)}
                  {v.value?.basis_quality ? ` · basis: ${v.value.basis_quality}` : ""}
                </div>
              </Card>

              <Card className="p-5">
                <h3 className="text-sm font-bold text-ip-ink">History</h3>
                <ol className="mt-3 space-y-3">
                  {audit.length === 0 && <li className="text-[13px] text-ip-ink-3">No recorded events.</li>}
                  {audit.map((a) => (
                    <li key={a.id} className="flex gap-3">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-ip-navy" />
                      <div>
                        <div className="text-[13px] font-semibold capitalize text-ip-ink">{a.action}</div>
                        <div className="text-[11px] text-ip-ink-3">{fmtDate(a.created_at)}</div>
                      </div>
                    </li>
                  ))}
                </ol>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-ip-line py-2 last:border-0">
      <span className="text-ip-ink-2">{k}</span>
      <span>{v}</span>
    </div>
  );
}
