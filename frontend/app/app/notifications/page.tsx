"use client";

import { useEffect, useState } from "react";
import { api, NotificationItem } from "@/lib/api";
import { PageHeader, Card, ErrorNote, Spinner, EmptyState, fmtDate } from "@/components/ui";

function humanize(type: string): string {
  return type.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function summary(payload: Record<string, unknown>): string {
  const keys = ["title", "project_name", "message", "name"];
  for (const k of keys) if (typeof payload[k] === "string") return payload[k] as string;
  const vals = Object.values(payload).filter((v) => typeof v === "string" || typeof v === "number");
  return vals.slice(0, 2).join(" · ");
}

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api.notifications().then(setItems).catch((e) => setError(e.message));
  }
  useEffect(() => { load(); }, []);

  async function markRead(id: string) {
    await api.markNotificationRead(id).catch(() => {});
    load();
  }
  async function markAll() {
    await api.markAllNotificationsRead().catch(() => {});
    load();
  }

  const unread = items?.filter((n) => !n.read).length ?? 0;

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Analysis results, review activity, and time-bar alerts."
        actions={unread > 0 ? <button onClick={markAll} className="btn-ghost">Mark all read</button> : undefined}
      />
      {error && <ErrorNote message={error} />}
      {!items && !error && <Spinner />}
      {items && items.length === 0 && <EmptyState title="You're all caught up" body="New analysis results and review activity will appear here." />}

      {items && items.length > 0 && (
        <Card className="divide-y divide-ip-line">
          {items.map((n) => (
            <div key={n.id} className={`flex items-start gap-3 px-4 py-3.5 ${n.read ? "" : "bg-ip-card-2"}`}>
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read ? "bg-ip-line-strong" : "bg-ip-orange"}`} />
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-semibold text-ip-ink">{humanize(n.type)}</div>
                <div className="truncate text-[13px] text-ip-ink-2">{summary(n.payload)}</div>
                <div className="mt-0.5 text-[11px] text-ip-ink-3">{fmtDate(n.created_at)}</div>
              </div>
              {!n.read && <button onClick={() => markRead(n.id)} className="shrink-0 text-[12px] font-semibold text-ip-navy hover:underline">Mark read</button>}
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
