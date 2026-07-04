"use client";

import { useEffect, useState } from "react";
import { api, AuditEntry } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState, fmtDate } from "@/components/ui";

const FILTERS = ["all", "variation", "project", "membership"] as const;
const actionTone: Record<string, string> = {
  created: "navy", confirmed: "recovery", approved: "recovery", rejected: "risk", deleted: "risk",
};

export default function AuditPage() {
  const { companyId, isAdmin } = useApp();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!companyId || !isAdmin) return;
    setRows(null);
    api.auditLog(companyId, filter === "all" ? undefined : filter).then(setRows).catch((e) => setError(e.message));
  }, [companyId, isAdmin, filter]);

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

      <div className="mb-6 flex gap-1 rounded-md border border-ip-line bg-ip-card p-1">
        {FILTERS.map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`rounded-sm px-3.5 py-1.5 text-sm font-semibold capitalize transition-colors ${filter === f ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"}`}>{f}</button>
        ))}
      </div>

      {!rows && !error && <Spinner />}
      {rows && rows.length === 0 && <EmptyState title="No audit events" body="Actions like creating projects and reviewing variations will be recorded here." />}

      {rows && rows.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ip-line">
                <th className="ip-th">When</th>
                <th className="ip-th">Entity</th>
                <th className="ip-th">Action</th>
                <th className="ip-th">Actor</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} className="ip-row hover:bg-ip-card-2">
                  <td className="px-4 py-3 text-sm tabular-nums text-ip-ink-2">{fmtDate(a.created_at)}</td>
                  <td className="px-4 py-3 text-sm"><Chip>{a.entity_type}</Chip> <span className="ml-1 font-mono text-[11px] text-ip-ink-3">{a.entity_id.slice(0, 8)}</span></td>
                  <td className="px-4 py-3 text-sm"><Chip tone={actionTone[a.action] ?? "neutral"}>{a.action}</Chip></td>
                  <td className="px-4 py-3 font-mono text-[11px] text-ip-ink-3">{a.actor_user_id ? a.actor_user_id.slice(0, 8) : "system"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
