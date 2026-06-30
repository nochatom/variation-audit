"use client";

import { ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";

type NavItem = { label: string; href: string; icon: ReactNode; adminOnly?: boolean };

const I = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]">
    <path d={d} />
  </svg>
);

const NAV: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: I("M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10") },
  { label: "Projects", href: "/projects", icon: I("M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z") },
  { label: "Documents", href: "/documents", icon: I("M7 3h7l5 5v13H5a1 1 0 01-1-1V4a1 1 0 011-1zM14 3v5h5M8 13h8M8 17h6") },
  { label: "Analysis", href: "/analysis", icon: I("M4 19V5M4 19h16M8 16V9M12 16v-4M16 16V7M20 16v-2") },
  { label: "Variations", href: "/variations", icon: I("M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11") },
  { label: "Evidence", href: "/evidence", icon: I("M10 3H4a1 1 0 00-1 1v16a1 1 0 001 1h16a1 1 0 001-1v-6M14 3h7v7M21 3l-9 9") },
  { label: "Reports", href: "/reports", icon: I("M3 3v18h18M7 14l3-3 3 3 5-6") },
  { label: "Audit", href: "/audit", icon: I("M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"), adminOnly: true },
  { label: "Notifications", href: "/notifications", icon: I("M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0") },
  { label: "Team", href: "/team", icon: I("M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8"), adminOnly: true },
  { label: "Settings", href: "/settings", icon: I("M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.9 2 2 0 11-2.8 2.8 1.7 1.7 0 00-2.9 1.2 2 2 0 11-4 0 1.7 1.7 0 00-2.9-1.2 2 2 0 11-2.8-2.8A1.7 1.7 0 003 12.6a2 2 0 010-1.2 1.7 1.7 0 00-1.2-2.9 2 2 0 112.8-2.8 1.7 1.7 0 002.9-1.2 2 2 0 014 0 1.7 1.7 0 002.9 1.2 2 2 0 112.8 2.8 1.7 1.7 0 00.4 2.4z") },
];

function navTitle(pathname: string): string {
  const item = NAV.find((n) => pathname === n.href || pathname.startsWith(n.href + "/"));
  return item?.label ?? "VariationIQ";
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

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { isAdmin, org } = useApp();
  const items = NAV.filter((n) => !n.adminOnly || isAdmin);

  const body = (
    <div className="flex h-full flex-col bg-ip-card">
      <div className="flex h-14 items-center gap-2.5 border-b border-ip-line px-5">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-ip-navy text-sm font-bold text-white">V</span>
        <span className="text-[15px] font-bold tracking-tight text-ip-ink">VariationIQ</span>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {items.map((n) => {
          const active = pathname === n.href || pathname.startsWith(n.href + "/");
          return (
            <Link
              key={n.href}
              href={n.href}
              onClick={onClose}
              className={`relative flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-semibold transition-colors ${
                active ? "bg-ip-card-2 text-ip-navy" : "text-ip-ink-2 hover:bg-ip-card-2 hover:text-ip-ink"
              }`}
            >
              {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-ip-navy" />}
              <span className={active ? "text-ip-navy" : "text-ip-ink-3"}>{n.icon}</span>
              {n.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-ip-line p-3">
        <div className="rounded-md border border-ip-line bg-ip-card-2 px-3 py-2">
          <div className="ip-label">Organization</div>
          <div className="mt-0.5 truncate text-[13px] font-semibold text-ip-ink">{org?.name ?? "—"}</div>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[244px] border-r border-ip-line lg:block">{body}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ip-navy/30" onClick={onClose} />
          <aside className="absolute inset-y-0 left-0 w-[244px] border-r border-ip-line shadow-ip-pop">{body}</aside>
        </div>
      )}
    </>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const { me, org, logout } = useApp();
  const [menu, setMenu] = useState(false);
  const [unread, setUnread] = useState(0);
  const initials = (me?.email ?? "?").slice(0, 2).toUpperCase();

  useEffect(() => {
    api.unreadCount().then((r) => setUnread(r.count)).catch(() => {});
  }, [pathname]);

  return (
    <header className="sticky top-0 z-20 border-b border-ip-line bg-ip-card/85 backdrop-blur-xl">
      <div className="flex h-14 items-center justify-between px-5 sm:px-8">
        <div className="flex items-center gap-3">
          <button onClick={onMenu} className="rounded-md p-1.5 text-ip-ink-2 hover:bg-ip-card-2 lg:hidden" aria-label="Open menu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
          </button>
          <span className="text-sm font-bold tracking-tight text-ip-ink">{navTitle(pathname)}</span>
        </div>

        <div className="relative flex items-center gap-3">
          <Link href="/notifications" className="relative rounded-md p-1.5 text-ip-ink-2 hover:bg-ip-card-2" aria-label="Notifications">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-5 w-5"><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0" /></svg>
            {unread > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-ip-orange ring-2 ring-ip-card" />}
          </Link>
          <span className="hidden rounded-pill border border-ip-line bg-ip-card-2 px-2.5 py-1 text-[12px] font-semibold text-ip-ink-2 sm:inline">
            {org?.role === "admin" ? "Admin" : "Member"}
          </span>
          <button onClick={() => setMenu((v) => !v)} className="grid h-8 w-8 place-items-center rounded-full bg-ip-navy text-[11px] font-bold text-white">
            {initials}
          </button>
          {menu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
              <div className="absolute right-0 top-11 z-20 w-56 rounded-lg border border-ip-line bg-ip-card p-1.5 shadow-ip-pop">
                <div className="border-b border-ip-line px-3 py-2">
                  <div className="truncate text-[13px] font-semibold text-ip-ink">{me?.email}</div>
                  <div className="text-[11px] text-ip-ink-3">{org?.name}</div>
                </div>
                <Link href="/settings" onClick={() => setMenu(false)} className="block rounded-md px-3 py-2 text-[13px] text-ip-ink-2 hover:bg-ip-card-2 hover:text-ip-ink">
                  Settings
                </Link>
                <button onClick={logout} className="block w-full rounded-md px-3 py-2 text-left text-[13px] text-ip-ink-2 hover:bg-ip-card-2 hover:text-ip-ink">
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
