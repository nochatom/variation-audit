"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, NotificationItem } from "@/lib/api";
import { PageHeader, Card, ErrorNote, Spinner, EmptyState, fmtDate } from "@/components/ui";

// Broadcast so the topbar bell (components/app/chrome.tsx) refreshes its unread
// badge immediately after a read action — without waiting for a route change.
export const NOTIFICATIONS_CHANGED = "notifications:changed";
function announceChange() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
}

function humanize(type: string): string {
  return type.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Render a human message per notification type. The analysis payloads only
// carry ids ({job_id, project_id, code}); surfacing those raw UUIDs is
// meaningless to a user, so we describe the event and link to the project
// instead of dumping ids into the row.
function describe(n: NotificationItem): { title: string; detail: string; href?: string } {
  const p = (n.payload ?? {}) as Record<string, unknown>;
  const projectId = typeof p.project_id === "string" ? p.project_id : undefined;
  const href = projectId ? `/app/projects/${projectId}` : undefined;
  switch (n.type) {
    case "analysis_complete":
      return { title: "Analysis complete", detail: "Variation detection finished — open the project to review results.", href };
    case "analysis_failed": {
      const code = typeof p.code === "string" ? p.code : null;
      const retryable = p.retryable === true ? " · retryable" : "";
      return { title: "Analysis failed", detail: code ? `Error ${code}${retryable}` : "The analysis job did not complete.", href };
    }
    default: {
      // Unknown type: prefer a readable field, but never render a bare UUID.
      const readable = ["title", "project_name", "message", "name"]
        .map((k) => p[k]).find((v) => typeof v === "string") as string | undefined;
      return { title: humanize(n.type), detail: readable ?? "", href };
    }
  }
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
    announceChange();
    load();
  }
  async function markAll() {
    await api.markAllNotificationsRead().catch(() => {});
    announceChange();
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
          {items.map((n) => {
            const d = describe(n);
            const Body = (
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-semibold text-ip-ink">{d.title}</div>
                {d.detail && <div className="truncate text-[13px] text-ip-ink-2">{d.detail}</div>}
                <div className="mt-0.5 text-[11px] text-ip-ink-3">{fmtDate(n.created_at)}</div>
              </div>
            );
            return (
              <div key={n.id} className={`flex items-start gap-3 px-4 py-3.5 ${n.read ? "" : "bg-ip-card-2"}`}>
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read ? "bg-ip-line-strong" : "bg-ip-orange"}`} />
                {d.href ? (
                  <Link href={d.href} onClick={() => !n.read && markRead(n.id)} className="min-w-0 flex-1 transition-opacity hover:opacity-80">
                    {Body}
                  </Link>
                ) : Body}
                {!n.read && <button onClick={() => markRead(n.id)} className="shrink-0 text-[12px] font-semibold text-ip-navy hover:underline">Mark read</button>}
              </div>
            );
          })}
        </Card>
      )}
    </div>
  );
}
