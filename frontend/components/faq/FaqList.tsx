"use client";

import { useMemo, useState } from "react";
import { FaqItem, FAQ_GROUP_LABEL, faqByGroup } from "@/lib/faq";

/** Built on <details>/<summary> rather than a `useState` accordion.
 *
 * The previous pricing-page FAQ rendered `{isOpen && <p>}`, so a closed answer
 * was not in the document at all: Ctrl+F could not find it, print dropped it,
 * and a crawler indexed one answer out of seven. <details> keeps every answer
 * in the DOM and brings keyboard and screen-reader behaviour with it, so
 * there is no aria-expanded to keep in sync. */
function Item({ item }: { item: FaqItem }) {
  return (
    <details id={item.id} className="scroll-mt-24 border-b border-ip-line">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-left [&::-webkit-details-marker]:hidden">
        <span className="text-[15px] font-semibold text-ip-ink">{item.q}</span>
        <svg
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          aria-hidden
          className="h-[18px] w-[18px] shrink-0 text-ip-ink-3 transition-transform duration-150 group-open:rotate-45"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
      </summary>
      <p className="max-w-[70ch] pb-5 text-[14.5px] leading-relaxed text-ip-ink-2">{item.a}</p>
    </details>
  );
}

/** `filterable` is off on the pricing page: seven questions in one list do not
 * need a search box, and an empty control reads as clutter. The full /faq page
 * turns it on because sixteen questions are scanned, not read. */
export function FaqList({
  items,
  grouped = false,
  filterable = false,
}: {
  items: FaqItem[];
  grouped?: boolean;
  filterable?: boolean;
}) {
  const [term, setTerm] = useState("");

  const shown = useMemo(() => {
    const t = term.trim().toLowerCase();
    if (!t) return items;
    return items.filter((i) => `${i.q} ${i.a}`.toLowerCase().includes(t));
  }, [items, term]);

  const groups = useMemo(() => (grouped ? faqByGroup(shown) : []), [grouped, shown]);

  return (
    <div>
      {filterable && (
        <div className="mb-10">
          <label htmlFor="faq-filter" className="mb-1.5 block text-[12px] font-semibold text-ip-ink-3">
            Find an answer
          </label>
          <input
            id="faq-filter"
            type="search"
            autoComplete="off"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="seats, limits, who can see our contracts…"
            aria-describedby="faq-count"
            className="w-full rounded-lg border border-ip-line-strong bg-ip-card px-4 py-3 text-[16px] text-ip-ink placeholder:text-ip-ink-3"
          />
          <p id="faq-count" role="status" aria-live="polite" className="mt-2 min-h-[1.4em] text-[13px] tabular-nums text-ip-ink-3">
            {term.trim() ? `${shown.length} ${shown.length === 1 ? "question matches" : "questions match"}` : ""}
          </p>
        </div>
      )}

      {shown.length === 0 && (
        <p className="py-8 text-[14px] text-ip-ink-3">
          No question matches that. Try a shorter phrase, or email us — the answer probably belongs
          on this page.
        </p>
      )}

      {grouped
        ? groups.map((g) => (
            <section key={g.group} className="mb-10 last:mb-0">
              <h2 className="ip-label mb-1 border-b border-ip-line pb-2.5">{FAQ_GROUP_LABEL[g.group]}</h2>
              {g.items.map((i) => (
                <Item key={i.id} item={i} />
              ))}
            </section>
          ))
        : (
          <div className="border-t border-ip-line">
            {shown.map((i) => (
              <Item key={i.id} item={i} />
            ))}
          </div>
        )}
    </div>
  );
}
