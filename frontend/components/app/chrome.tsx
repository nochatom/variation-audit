"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, NotificationItem } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useTheme } from "@/lib/use-theme";
import { fmtDate } from "@/components/ui";
import { LogoMark } from "@/components/ui/Logo";
import { Wordmark } from "@/components/ui/Wordmark";

type NavItem = {
  label: string;
  href: string;
  icon: ReactNode;
  adminOnly?: boolean;
  /** Renders the pending-review count and the time-bar flag. Exactly one item
   *  carries this: the sidebar has a single protagonist, and a badge on every
   *  row would restore the flat "everything is equally important" list this
   *  grouping exists to break. */
  primary?: boolean;
};

/** Groups make the product's actual sequence legible: set a project up, feed
 *  it documents, run detection — then work the queue that detection produces.
 *  Admin is a different job on a different cadence, so it sits apart at the
 *  bottom rather than interleaved with daily work. */
type NavGroup = { label: string | null; items: NavItem[]; admin?: boolean };

const I = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">
    <path d={d} />
  </svg>
);

const NAV: NavGroup[] = [
  // Unlabelled: Dashboard is the landing surface, and a header above the very
  // first row buys nothing but vertical noise.
  {
    label: null,
    items: [
      { label: "Dashboard", href: "/app/dashboard", icon: I("M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10") },
    ],
  },
  {
    label: "Set up",
    items: [
      { label: "Projects", href: "/app/projects", icon: I("M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z") },
      { label: "Documents", href: "/app/documents", icon: I("M7 3h7l5 5v13H5a1 1 0 01-1-1V4a1 1 0 011-1zM14 3v5h5M8 13h8M8 17h6") },
      { label: "Analysis", href: "/app/analysis", icon: I("M4 19V5M4 19h16M8 16V9M12 16v-4M16 16V7M20 16v-2") },
    ],
  },
  {
    label: "Recover",
    items: [
      { label: "Variations", href: "/app/variations", icon: I("M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"), primary: true },
      { label: "Evidence", href: "/app/evidence", icon: I("M10 3H4a1 1 0 00-1 1v16a1 1 0 001 1h16a1 1 0 001-1v-6M14 3h7v7M21 3l-9 9") },
      { label: "Reports", href: "/app/reports", icon: I("M3 3v18h18M7 14l3-3 3 3 5-6") },
    ],
  },
  // Notifications is intentionally NOT a sidebar item — the topbar bell icon
  // is the single entry point and opens the notifications popover. The page
  // itself stays reachable via the popover's "View all notifications" link
  // (and its topbar title is preserved in NESTED_TITLES below).
  {
    label: "Manage",
    admin: true,
    items: [
      // Not adminOnly: every member can read the org's entity details and offices
      // (GET /orgs/{id} is member-open); only writes require admin.
      { label: "Organisation", href: "/app/organisation", icon: I("M3 21h18M5 21V7l7-4 7 4v14M9 21v-4h6v4M9 10h.01M12 10h.01M15 10h.01M9 13h.01M12 13h.01M15 13h.01") },
      { label: "Team", href: "/app/team", icon: I("M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8"), adminOnly: true },
      { label: "Audit", href: "/app/audit", icon: I("M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"), adminOnly: true },
      { label: "Settings", href: "/app/settings", icon: I("M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.9 2 2 0 11-2.8 2.8 1.7 1.7 0 00-2.9 1.2 2 2 0 11-4 0 1.7 1.7 0 00-2.9-1.2 2 2 0 11-2.8-2.8A1.7 1.7 0 003 12.6a2 2 0 010-1.2 1.7 1.7 0 00-1.2-2.9 2 2 0 112.8-2.8 1.7 1.7 0 002.9-1.2 2 2 0 014 0 1.7 1.7 0 002.9 1.2 2 2 0 112.8 2.8 1.7 1.7 0 00.4 2.4z") },
    ],
  },
];

// Nested settings routes (not their own NAV entry) get a more specific
// topbar title than the generic "Settings" match below — otherwise the
// topbar disagrees with the page's own <h1> (e.g. "Settings" shown while
// viewing "Billing & subscription").
const NESTED_TITLES: { prefix: string; title: string }[] = [
  { prefix: "/app/settings/billing", title: "Billing & subscription" },
  // Notifications has no sidebar NAV entry (see NAV above), so its topbar
  // title is mapped here to keep the header correct on /app/notifications.
  { prefix: "/app/notifications", title: "Notifications" },
];

/** Every nav item, ignoring grouping — grouping is a presentation concern, so
 *  title lookup and any other route matching should not have to know about it. */
const NAV_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

function navTitle(pathname: string): string {
  const nested = NESTED_TITLES.find((n) => pathname === n.prefix || pathname.startsWith(n.prefix + "/"));
  if (nested) return nested.title;
  const item = NAV_ITEMS.find((n) => pathname === n.href || pathname.startsWith(n.href + "/"));
  return item?.label ?? "VariationiQ";
}

export function AppChrome({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      <div className="flex min-h-screen flex-col lg:pl-[244px]">
        <Topbar onMenu={() => setOpen(true)} />
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-5 py-8 sm:px-8">{children}</main>
      </div>
    </div>
  );
}

// Must match .animate-drawer-out's duration in globals.css (200ms) — the
// drawer stays mounted this long after close so the slide-out can finish.
const DRAWER_EXIT_MS = 200;

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { isAdmin, org, companyId } = useApp();
  const groups = NAV.map((g) => ({ ...g, items: g.items.filter((n) => !n.adminOnly || isAdmin) }))
    .filter((g) => g.items.length > 0);
  const [rendered, setRendered] = useState(open);
  const [closing, setClosing] = useState(false);
  // The two numbers the product exists to surface: work waiting on a decision,
  // and work about to expire. Both come from one call the dashboard already
  // makes, and both fail silently — a sidebar must never break on a bad fetch.
  const [pending, setPending] = useState<number | null>(null);
  const [atRisk, setAtRisk] = useState(0);

  useEffect(() => {
    if (!companyId) return;
    let live = true;
    api
      .orgDashboard(companyId)
      .then((d) => {
        if (!live) return;
        setPending(d.totals.pending);
        setAtRisk(d.projects.reduce((n, p) => n + p.time_bar_at_risk, 0));
      })
      .catch(() => {});
    return () => {
      live = false;
    };
    // Re-read on navigation so approving a variation is reflected without a reload.
  }, [companyId, pathname]);

  useEffect(() => {
    if (open) {
      setRendered(true);
      setClosing(false);
    } else if (rendered) {
      setClosing(true);
      const t = setTimeout(() => {
        setRendered(false);
        setClosing(false);
      }, DRAWER_EXIT_MS);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const body = (
    <div className="flex h-full flex-col bg-ip-card">
      <Link
        href="/app/dashboard"
        className="flex h-14 items-center gap-2.5 border-b border-ip-line px-5 cursor-pointer transition hover:opacity-80"
        aria-label="VariationiQ home"
      >
        <LogoMark size={28} />
        <Wordmark height={17} className="text-ip-ink" />
      </Link>

      {/* flex-col so the admin group's mt-auto can push it to the bottom */}
      <nav className="flex flex-1 flex-col overflow-y-auto p-3">
        {groups.map((g, gi) => (
          <div
            key={g.label ?? "root"}
            className={
              // "Manage" is pushed to the bottom rather than shrunk: demoting by
              // font size would trade hierarchy for legibility, which this
              // system doesn't allow. Position and separation do the work.
              g.admin ? "mt-auto border-t border-ip-line pt-3" : gi > 0 ? "mt-5" : ""
            }
          >
            {g.label && <div className="ip-label mb-1.5 px-3">{g.label}</div>}
            <div className="space-y-0.5">
              {g.items.map((n) => {
                const active = pathname === n.href || pathname.startsWith(n.href + "/");
                // One pill, not two. The count is the size of the queue; the
                // colour is whether any of it is expiring. Two adjacent numeric
                // pills read as a single garbled number ("2 4") and force the
                // user to learn a colour key just to parse the sidebar.
                const showCount = n.primary && pending !== null && pending > 0;
                const urgent = atRisk > 0;
                const countLabel = urgent
                  ? `${pending} awaiting review, ${atRisk} near the time bar`
                  : `${pending} variation${pending === 1 ? "" : "s"} awaiting review`;
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    onClick={onClose}
                    aria-current={active ? "page" : undefined}
                    className={`group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-[background-color,color] duration-150 ease-out ${
                      active
                        ? "bg-ip-navy/[0.07] font-semibold text-ip-navy"
                        : "text-ip-ink-2 hover:bg-ip-card-2 hover:text-ip-ink"
                    }`}
                  >
                    <span
                      className={`transition-colors duration-150 ${
                        active ? "text-ip-navy" : "text-ip-ink-3 group-hover:text-ip-ink-2"
                      }`}
                    >
                      {n.icon}
                    </span>
                    <span className="flex-1 truncate">{n.label}</span>
                    {showCount && (
                      <span
                        className={`rounded-pill px-1.5 py-px text-[11px] font-bold tabular-nums ${
                          // Not hue alone (WCAG 1.4.1): the urgent pill is a pale
                          // tint with dark text, the normal one a solid dark fill
                          // with white text — they invert in greyscale, so the
                          // states stay distinguishable without colour vision.
                          urgent ? "bg-ip-orange/12 text-ip-orange-2" : "bg-ip-navy-fill text-white"
                        }`}
                        // title serves the mouse; aria-label carries the same
                        // meaning to assistive tech, which does not reliably
                        // announce title.
                        title={countLabel}
                        aria-label={countLabel}
                      >
                        {pending}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Card chrome removed: a border, a fill and an "ORGANIZATION" label to
          render one string. The name is what matters — it stays, quietly. */}
      <div className="border-t border-ip-line px-4 py-3">
        <div className="truncate text-[12px] font-medium text-ip-ink-3" title={org?.name ?? undefined}>
          {org?.name ?? "—"}
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[244px] border-r border-ip-line lg:block">{body}</aside>
      {rendered && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className={`absolute inset-0 bg-ip-navy/30 ${closing ? "animate-backdrop-out" : "animate-backdrop-in"}`}
            onClick={onClose}
          />
          <aside
            className={`absolute inset-y-0 left-0 w-[244px] border-r border-ip-line shadow-ip-pop ${
              closing ? "animate-drawer-out" : "animate-drawer-in"
            }`}
          >
            {body}
          </aside>
        </div>
      )}
    </>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const { me, org, logout } = useApp();
  const { theme, toggleTheme } = useTheme();
  const [menu, setMenu] = useState(false);
  const initials = (me?.email ?? "?").slice(0, 2).toUpperCase();

  return (
    <header className="sticky top-0 z-20 border-b border-ip-line bg-ip-card/85 backdrop-blur-xl">
      <div className="flex h-14 items-center justify-between px-5 sm:px-8">
        <div className="flex items-center gap-3">
          <button onClick={onMenu} className="rounded-md p-1.5 text-ip-ink-2 transition-colors hover:bg-ip-card-2 active:scale-90 lg:hidden" aria-label="Open menu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
          </button>
          <span className="text-sm font-bold tracking-tight text-ip-ink">{navTitle(pathname)}</span>
        </div>

        <div className="relative flex items-center gap-3">
          <button
            onClick={toggleTheme}
            className="rounded-md p-1.5 text-ip-ink-2 transition-colors hover:bg-ip-card-2 active:scale-90"
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" /></svg>
            )}
          </button>
          <NotificationBell />
          <span className="hidden rounded-pill border border-ip-line bg-ip-card-2 px-2.5 py-1 text-[12px] font-semibold text-ip-ink-2 sm:inline">
            {org?.role === "admin" ? "Admin" : "Member"}
          </span>
          <button
            onClick={() => setMenu((v) => !v)}
            className="grid h-8 w-8 place-items-center rounded-full bg-ip-navy-fill text-[11px] font-bold text-white transition-transform active:scale-90"
          >
            {initials}
          </button>
          {menu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
              <div className="animate-scale-in absolute right-0 top-11 z-20 w-56 origin-top-right rounded-lg border border-ip-line bg-ip-card p-1.5 shadow-ip-pop">
                <div className="border-b border-ip-line px-3 py-2">
                  <div className="truncate text-[13px] font-semibold text-ip-ink">{me?.email}</div>
                  <div className="text-[11px] text-ip-ink-3">{org?.name}</div>
                </div>
                <Link href="/app/settings" onClick={() => setMenu(false)} className="block rounded-md px-3 py-2 text-[13px] text-ip-ink-2 transition-colors hover:bg-ip-card-2 hover:text-ip-ink">
                  Settings
                </Link>
                <button onClick={logout} className="block w-full rounded-md px-3 py-2 text-left text-[13px] text-ip-ink-2 transition-colors hover:bg-ip-card-2 hover:text-ip-ink">
                  Log out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

/* Notification bell + popover.
 *
 * Opening the popover is NOT navigation — it's an overlay over the current
 * page — so the active sidebar item is unaffected. The "Notifications" nav
 * item highlights only when the user actually navigates to /app/notifications
 * (via "View all" or the sidebar), never merely by opening this popup. */
function NotificationBell() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[] | null>(null);

  const refreshCount = useCallback(() => {
    api.unreadCount().then((r) => setUnread(r.count)).catch(() => {});
  }, []);

  useEffect(() => {
    refreshCount();
    // Stay in sync with read actions elsewhere (e.g. the notifications page),
    // which broadcast this event — no route change fires there.
    window.addEventListener("notifications:changed", refreshCount);
    return () => window.removeEventListener("notifications:changed", refreshCount);
  }, [pathname, refreshCount]);

  // Close the popover whenever the route changes (e.g. after clicking through
  // to a project or "View all").
  useEffect(() => { setOpen(false); }, [pathname]);

  // Escape closes the popover (keyboard a11y + click-outside parity).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function toggle() {
    if (open) { setOpen(false); return; }
    setOpen(true);
    const list = await api.notifications().catch(() => [] as NotificationItem[]);
    setItems(list.slice(0, 6));
  }

  async function markAll() {
    if (unread === 0) return;
    // Optimistic: clear the badge and mark visible rows read instantly, then
    // persist. markAllNotificationsRead clears ALL unread server-side (not
    // just the visible 6), so the refetched count comes back 0 too.
    setUnread(0);
    setItems((prev) => prev?.map((n) => ({ ...n, read: true })) ?? null);
    await api.markAllNotificationsRead().catch(() => {});
    window.dispatchEvent(new Event("notifications:changed"));
  }

  return (
    <div className="relative">
      <button
        onClick={toggle}
        aria-label="Notifications"
        aria-expanded={open}
        className="relative rounded-md p-1.5 text-ip-ink-2 transition-colors hover:bg-ip-card-2 active:scale-90"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-5 w-5"><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0" /></svg>
        {unread > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-ip-orange ring-2 ring-ip-card" />}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="animate-scale-in absolute right-0 top-11 z-20 w-80 origin-top-right overflow-hidden rounded-lg border border-ip-line bg-ip-card shadow-ip-pop">
            <div className="flex items-center justify-between border-b border-ip-line px-3.5 py-2.5">
              <span className="inline-flex items-center gap-2 text-[13px] font-semibold text-ip-ink">
                Notifications
                {unread > 0 && (
                  <span className="rounded-pill bg-ip-orange/12 px-1.5 py-px text-[10px] font-bold tabular-nums text-ip-orange-2">{unread}</span>
                )}
              </span>
              {/* Top-right action. Disabled (muted, non-interactive) when there
                  is nothing unread, so the control stays discoverable without
                  jumping in and out of the layout. */}
              <button
                onClick={markAll}
                disabled={unread === 0}
                className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-[12px] font-semibold text-ip-navy transition-colors hover:text-ip-navy/75 disabled:cursor-default disabled:text-ip-ink-3 disabled:hover:text-ip-ink-3"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
                Mark all as read
              </button>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {items === null ? (
                <div className="px-3.5 py-6 text-center text-[13px] text-ip-ink-3">Loading…</div>
              ) : items.length === 0 ? (
                <div className="px-3.5 py-6 text-center text-[13px] text-ip-ink-3">You&apos;re all caught up.</div>
              ) : (
                <ul className="divide-y divide-ip-line">
                  {items.map((n) => {
                    const d = describeNotif(n);
                    return (
                      <li key={n.id}>
                        <Link
                          href={d.href}
                          onClick={() => setOpen(false)}
                          aria-label={`${n.read ? "" : "Unread: "}${d.title}`}
                          className={`flex items-start gap-2.5 px-3.5 py-2.5 transition-colors hover:bg-ip-card-2 ${n.read ? "" : "bg-ip-navy/[0.045]"}`}
                        >
                          {/* Unread: solid orange dot. Read: hollow ring — a
                              clear, quiet distinction between the two states. */}
                          <span
                            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read ? "ring-1 ring-inset ring-ip-line-strong" : "bg-ip-orange"}`}
                            aria-hidden
                          />
                          <span className="min-w-0 flex-1">
                            <span className={`block text-[13px] ${n.read ? "font-medium text-ip-ink-2" : "font-semibold text-ip-ink"}`}>{d.title}</span>
                            {d.detail && <span className="block truncate text-[12px] text-ip-ink-3">{d.detail}</span>}
                            <span className="mt-0.5 block text-[11px] text-ip-ink-3">{fmtDate(n.created_at)}</span>
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <Link
              href="/app/notifications"
              onClick={() => setOpen(false)}
              className="block border-t border-ip-line px-3.5 py-2.5 text-center text-[12px] font-semibold text-ip-navy transition-colors hover:bg-ip-card-2"
            >
              View all notifications
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

// Compact per-type description for the popover — mirrors the notifications
// page, and never renders a raw payload UUID.
function describeNotif(n: NotificationItem): { title: string; detail: string; href: string } {
  const p = (n.payload ?? {}) as Record<string, unknown>;
  const projectId = typeof p.project_id === "string" ? p.project_id : undefined;
  const href = projectId ? `/app/projects/${projectId}` : "/app/notifications";
  if (n.type === "analysis_complete") return { title: "Analysis complete", detail: "Variation detection finished.", href };
  if (n.type === "analysis_failed") {
    const code = typeof p.code === "string" ? p.code : null;
    return { title: "Analysis failed", detail: code ? `Error ${code}` : "The analysis job did not complete.", href };
  }
  const title = n.type.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return { title, detail: "", href };
}
