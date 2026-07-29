"use client";

import { useEffect, useMemo, useState } from "react";
import { api, AuditEntry } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, ErrorNote, Spinner, EmptyState } from "@/components/ui";

/* An audit entry is a sentence, not a database row. "Sarah Chen changed
 * Oualid's role" is scannable without column headers; "membership a3f2b891 /
 * role_changed / 8f31a204" is not, and that was the whole failure of the
 * previous table — the one screen whose purpose is accountability could not
 * say who did what.
 *
 * actor_name and entity_label are resolved server-side (routers/audit.py).
 * Both can be null — a system event has no actor, and an append-only log keeps
 * entries for entities that were later deleted — so every path below degrades
 * to something readable rather than printing a raw UUID. */

/** `types: null` means no filtering. Explicitly typed rather than `as const`:
 *  a const tuple union makes `types[0]` unindexable for TypeScript. */
type FilterDef = { key: string; label: string; types: string[] | null };
const FILTERS: FilterDef[] = [
  { key: "all", label: "Everything", types: null },
  { key: "membership", label: "People", types: ["membership", "invitation"] },
  { key: "project", label: "Projects", types: ["project"] },
  { key: "subscription", label: "Billing", types: ["subscription", "invoice", "payment"] },
  { key: "variation", label: "Variations", types: ["variation"] },
];

/* Severity by VERB, keyed on the part after the dot.
 *
 * The previous map keyed on five bare verbs — created, confirmed, approved,
 * rejected, deleted — and the backend writes 26 actions, every one in
 * namespace.verb form. Not one matched, so every chip fell through to
 * "neutral": the page looked colour-coded and was not. Keying on the verb
 * covers all 26 and any future action that follows the same convention. */
type Tone = "create" | "change" | "remove" | "money";
const VERB_TONE: Record<string, Tone> = {
  created: "create", added: "create", accepted: "create", unarchived: "create",
  updated: "change", role_changed: "change", reopened: "change",
  logo_updated: "change", reactivated: "change", upgraded: "change",
  deleted: "remove", removed: "remove", revoked: "remove", archived: "remove",
  canceled: "remove", cancel_requested: "remove", suspended: "remove",
  paid: "money", succeeded: "money", failed: "money", voided: "money",
  checkout_started: "money", accessed: "money",
};
const TONE_DOT: Record<Tone, string> = {
  create: "bg-ip-recovery",
  change: "bg-ip-orange",
  remove: "bg-ip-risk",
  money: "bg-ip-navy",
};

function toneOf(action: string): Tone {
  const verb = action.includes(".") ? action.slice(action.indexOf(".") + 1) : action;
  return VERB_TONE[verb] ?? "change";
}

/** "member.role_changed" -> "changed role". Falls back to the raw action so an
 *  unmapped verb is still legible rather than blank. */
function phrase(a: AuditEntry): string {
  const verb = a.action.includes(".") ? a.action.slice(a.action.indexOf(".") + 1) : a.action;
  const words = verb.replace(/_/g, " ");
  const noun = a.entity_label ?? `${a.entity_type} ${a.entity_id.slice(0, 8)}`;
  switch (a.entity_type) {
    case "membership":
      return `${words} ${noun}`;
    case "subscription":
      return `${words} the subscription`;
    default:
      return `${words} ${noun}`;
  }
}

function initials(name: string): string {
  const parts = name.replace(/@.*$/, "").split(/[\s._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function relative(iso: string): string {
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function dayKey(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toDateString();
}

function dayLabel(iso: string): { title: string; sub: string } {
  const d = new Date(iso);
  const today = new Date().toDateString();
  const yest = new Date(Date.now() - 864e5).toDateString();
  const k = d.toDateString();
  const sub = d.toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long" });
  if (k === today) return { title: "Today", sub };
  if (k === yest) return { title: "Yesterday", sub };
  return { title: sub, sub: d.toLocaleDateString("en-AU", { year: "numeric" }) };
}

const LIMIT = 100;

export default function AuditPage() {
  const { companyId, isAdmin } = useApp();
  const [filter, setFilter] = useState<string>("all");
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId || !isAdmin) return;
    setRows(null);
    // The endpoint takes a single entity_type. Groups covering several types
    // fetch everything and narrow on the client rather than firing one request
    // per type — the page is capped at LIMIT either way.
    const single = FILTERS.find((f) => f.key === filter);
    const serverType = single?.types?.length === 1 ? single.types[0] : undefined;
    api.auditLog(companyId, serverType, LIMIT).then(setRows).catch((e) => setError(e.message));
  }, [companyId, isAdmin, filter]);

  const shown = useMemo(() => {
    if (!rows) return null;
    const f = FILTERS.find((x) => x.key === filter);
    if (!f?.types) return rows;
    return rows.filter((r) => f.types!.includes(r.entity_type));
  }, [rows, filter]);

  const days = useMemo(() => {
    if (!shown) return [];
    const out: { key: string; entries: AuditEntry[] }[] = [];
    for (const e of shown) {
      const k = dayKey(e.created_at);
      const last = out[out.length - 1];
      if (last && last.key === k) last.entries.push(e);
      else out.push({ key: k, entries: [e] });
    }
    return out;
  }, [shown]);

  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="Audit Trail" description="An immutable record of every change in your organization." />
        <EmptyState title="Admin access required" body="The audit trail is visible to organization admins only. Ask an admin to grant you the admin role in Team." />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Audit Trail" description="An immutable, time-ordered record of every change — who did what, and when." />
      {error && <ErrorNote message={error} />}

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="inline-flex gap-0.5 rounded-md border border-ip-line bg-ip-card p-0.5" role="group" aria-label="Filter by area">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              aria-pressed={filter === f.key}
              className={`rounded-sm px-3 py-1.5 text-[12.5px] font-semibold transition-colors ${
                filter === f.key ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {/* The endpoint silently returns a slice; say so rather than implying
            this is the whole history. */}
        {shown && shown.length > 0 && (
          <span className="ml-auto text-[12.5px] text-ip-ink-3">
            {shown.length === LIMIT ? `Showing the ${LIMIT} most recent` : `${shown.length} event${shown.length === 1 ? "" : "s"}`}
          </span>
        )}
      </div>

      {!rows && !error && <Spinner />}
      {shown && shown.length === 0 && (
        <EmptyState title="No audit events" body="Actions like creating projects and reviewing variations will be recorded here." />
      )}

      {days.map(({ key, entries }) => {
        const { title, sub } = dayLabel(entries[0].created_at);
        return (
          <section key={key}>
            <div className="mt-7 flex items-baseline justify-between gap-4 border-b-[1.5px] border-ip-ink pb-1.5">
              <h2 className="text-[13px] font-bold tracking-[-0.01em] text-ip-ink">{title}</h2>
              <span className="text-[11.5px] text-ip-ink-3">{sub}</span>
            </div>
            <ul>
              {entries.map((a) => {
                const who = a.actor_name;
                const time = new Date(a.created_at);
                return (
                  <li key={a.id} className="grid grid-cols-[54px_1fr_auto] items-baseline gap-x-3 border-b border-ip-line py-2.5">
                    <span className="whitespace-nowrap text-[12px] tabular-nums text-ip-ink-3">
                      {isNaN(time.getTime()) ? "—" : time.toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit", hour12: false })}
                    </span>
                    <span className="text-[14px] text-ip-ink">
                      <span className={`mr-1.5 inline-block h-[7px] w-[7px] rounded-[2px] align-[1px] ${TONE_DOT[toneOf(a.action)]}`} aria-hidden />
                      {who ? (
                        <span className="inline-flex items-center gap-1.5 font-semibold">
                          <span className="inline-grid h-[18px] w-[18px] flex-none place-items-center rounded-[5px] bg-ip-navy-fill text-[9.5px] font-bold text-white">
                            {initials(who)}
                          </span>
                          {who}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 font-semibold text-ip-ink-2">
                          <span className="inline-grid h-[18px] w-[18px] flex-none place-items-center rounded-[5px] border border-ip-line-strong text-[9px] font-bold text-ip-ink-3">
                            SYS
                          </span>
                          System
                        </span>
                      )}{" "}
                      {phrase(a)}
                    </span>
                    <span className="whitespace-nowrap text-[11.5px] text-ip-ink-3">{relative(a.created_at)}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
