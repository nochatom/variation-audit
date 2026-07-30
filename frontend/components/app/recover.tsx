/**
 * Shared vocabulary for the Recover flow (Variations queue, variation detail,
 * Evidence library, Reports).
 *
 * These four screens are one job split across four views: find what was never
 * claimed, read the proof, decide, then export the position. They earn shared
 * primitives rather than four sets of lookalike markup — the evidence spine in
 * particular renders from one component in both the detail page and the
 * Evidence library, so the two can't drift.
 *
 * Everything here is built from existing Ironclad `ip-*` tokens and Public
 * Sans. No new colours, no second typeface.
 */
import { ReactNode } from "react";
import { EvidenceContext } from "@/lib/api";
import { aud } from "@/components/ui";

/** Day-precision date. The spine argues a sequence of days; a timestamp down
 *  to the minute is noise at that scale. */
export function fmtDay(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

/** The action names the user clicked, not the status the API stores. A button
 *  labelled "Approve" has to produce a state labelled "Approved". */
export const STATUS_LABEL: Record<string, string> = {
  pending: "Pending review",
  confirmed: "Approved",
  rejected: "Rejected",
};

/**
 * Section heading: a label and a hairline, not a card.
 *
 * Boxing every block is what flattened these screens into grids of equal
 * panels — a card says "this is a thing", and most of these blocks are
 * sections of one argument, not separate things.
 */
export function Section({
  title,
  meta,
  action,
  children,
  className = "",
}: {
  title: string;
  meta?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`mb-10 last:mb-0 ${className}`}>
      <div className="mb-4 flex items-baseline gap-3">
        <h2 className="ip-label">{title}</h2>
        {meta && <span className="text-[11px] text-ip-ink-3">{meta}</span>}
        <span className="h-px flex-1 bg-ip-line" aria-hidden />
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** Sidebar rail section — qualifiers on the claim, deliberately quieter than
 *  a Section in the main column. */
export function RailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="ip-label mb-3 border-b border-ip-line pb-2">{title}</h2>
      {children}
    </section>
  );
}

export function Fact({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-[7px]">
      <span className="text-[13px] text-ip-ink-3">{k}</span>
      <span className="text-right">{v}</span>
    </div>
  );
}

export function Money({ n, strong = false }: { n: number | null | undefined; strong?: boolean }) {
  return (
    <span className={`text-[13px] tabular-nums ${strong ? "font-bold text-ip-ink" : "font-medium text-ip-ink-2"}`}>
      {aud(n)}
    </span>
  );
}

/**
 * A statement set as a statement.
 *
 * The register for every headline figure in this flow: the number leads, but
 * it sits inside a sentence so the hedge stays welded to it. A bare figure at
 * 52px reads as settled, and nothing here is settled until a reviewer says so.
 * Used for the finding on the detail page and the position on the queue.
 */
export function Claim({
  children,
  /** Screens where the claim *is* the page headline pass "h1" — a page whose
   *  largest text is a <p> leaves screen readers with no heading to land on. */
  as: Tag = "p",
}: {
  children: ReactNode;
  as?: "p" | "h1" | "h2";
}) {
  return (
    <Tag className="max-w-[34ch] text-[26px] font-semibold leading-[1.25] tracking-display text-ip-ink sm:max-w-[46ch] sm:text-[30px]">
      {children}
    </Tag>
  );
}

/** Secondary line under a Claim — resets the display tracking so it reads as
 *  prose rather than a shrunken headline. */
export function ClaimNote({ children }: { children: ReactNode }) {
  return (
    <span className="mt-3 block text-[14px] font-medium leading-normal tracking-normal text-ip-ink-3">
      {children}
    </span>
  );
}

/**
 * Time-bar notice. Asymmetric by design: on track is a quiet line in a rail,
 * at risk interrupts the page. Nothing else in this product can make a claim
 * worthless on its own.
 */
export function TimeBarNotice({ children }: { children: ReactNode }) {
  return (
    <div className="flex gap-3 rounded-md border border-ip-risk/30 border-l-[3px] border-l-ip-risk bg-ip-risk-bg px-4 py-3">
      <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0 text-ip-risk" fill="currentColor" aria-hidden>
        <path d="M12 2L1 21h22L12 2zm0 6l7 12H5l7-12zm-1 3v4h2v-4h-2zm0 5v2h2v-2h-2z" />
      </svg>
      <p className="text-[13px] leading-relaxed text-ip-risk">{children}</p>
    </div>
  );
}

/** Basis quality is the honest qualifier on an estimate, so a weak basis is
 *  marked. --ip-warn exists for exactly this middle severity and is text-safe,
 *  unlike --ip-orange. */
export function BasisQuality({ quality }: { quality: string | null | undefined }) {
  if (!quality) return <span className="text-[13px] text-ip-ink-3">—</span>;
  const weak = /assum|infer|low|weak|estimat/i.test(quality);
  return (
    <span
      className={`inline-flex items-center rounded-pill px-2 py-0.5 text-[11px] font-semibold capitalize ${
        weak ? "bg-ip-warn-bg text-ip-warn" : "bg-ip-card-3 text-ip-ink-2"
      }`}
    >
      {quality}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Evidence spine
// ---------------------------------------------------------------------------

/** Chronological order is the argument: an instruction, then the work, then
 *  the record of it. A Security of Payment claim is won on that sequence.
 *  Undated sources can't take a position in it, so they sit at the end rather
 *  than faking one. */
export function sortChronologically(evidence: EvidenceContext[]): EvidenceContext[] {
  return [...evidence]
    .map((e, i) => ({ e, i, t: e.source_document?.doc_timestamp ? Date.parse(e.source_document.doc_timestamp) : NaN }))
    .sort((a, b) => {
      if (isNaN(a.t) && isNaN(b.t)) return a.i - b.i;
      if (isNaN(a.t)) return 1;
      if (isNaN(b.t)) return -1;
      return a.t - b.t;
    })
    .map(({ e }) => e);
}

/**
 * One source, hung off the spine.
 *
 * The quote is set at 16px — larger than every piece of interface around it.
 * That inverts the usual dashboard hierarchy where chrome is loud and content
 * is 13px italic: the quoted site instruction is what the reviewer came to
 * read, so the provenance line above it is the caption, not the other way
 * round.
 */
function EvidenceNode({ e, last }: { e: EvidenceContext; last: boolean }) {
  const doc = e.source_document;
  const day = fmtDay(doc?.doc_timestamp);
  const source = doc?.source;

  return (
    <li className="relative pb-7 pl-8 last:pb-0">
      {!last && <span className="absolute left-[3.5px] top-3 h-full w-px bg-ip-line" aria-hidden />}
      <span
        className="absolute left-0 top-[5px] h-2 w-2 rounded-full border-2 border-ip-navy-3 bg-ip-bg"
        aria-hidden
      />

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] tabular-nums text-ip-ink">
          {day ?? "Undated"}
        </span>
        <span className="inline-flex items-center gap-1 rounded-pill bg-ip-navy/10 px-2 py-0.5 text-[11px] font-semibold text-ip-navy">
          {e.type}
        </span>
        {e.reference && (
          <span className="text-[12px] font-semibold tabular-nums text-ip-ink-2">{e.reference}</span>
        )}
        {source && <span className="truncate text-[12px] text-ip-ink-3">{source}</span>}
      </div>

      {e.quote ? (
        <blockquote className="relative mt-2.5 max-w-[62ch] pl-5 text-[16px] leading-[1.65] text-ip-ink">
          {/* Public Sans's own quote glyph — the app is single-family by
              design, so a decorative serif here would break the system for a
              piece of punctuation. */}
          <span className="absolute left-0 top-[1px] text-[24px] font-bold leading-none text-ip-line-strong" aria-hidden>
            &ldquo;
          </span>
          {e.quote}
        </blockquote>
      ) : (
        <p className="mt-2 text-[13px] text-ip-ink-3">
          Linked without a quoted passage — open the source document to read it in context.
        </p>
      )}
    </li>
  );
}

/**
 * The evidence spine: sources on a hairline rail in date order.
 *
 * Rendered from this one component on both the variation detail page and the
 * Evidence library, so a reviewer reads the same proof the same way whichever
 * door they came in through.
 */
export function EvidenceSpine({
  items,
  empty,
}: {
  items: EvidenceContext[];
  /** Context-specific empty state — what to do about it differs by screen. */
  empty: ReactNode;
}) {
  const timeline = sortChronologically(items);
  if (timeline.length === 0) return <>{empty}</>;
  return (
    <ol className="mt-1">
      {timeline.map((e, i) => (
        <EvidenceNode key={i} e={e} last={i === timeline.length - 1} />
      ))}
    </ol>
  );
}

/** Label for a spine's `meta` slot, honest about undated sources rather than
 *  claiming an order it doesn't have. */
export function spineMeta(items: EvidenceContext[]): string {
  const n = items.length;
  const undated = items.filter((e) => !e.source_document?.doc_timestamp).length;
  const noun = n === 1 ? "source" : "sources";
  if (undated === n) return `${n} ${noun}, none dated`;
  if (undated > 0) return `${n} ${noun}, oldest first · ${undated} undated`;
  return `${n} ${noun}, oldest first`;
}
