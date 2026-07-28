/**
 * VariationiQ design-reference shell (vq).
 *
 * The permanent frame: 240px sidebar, 72px top bar, #F6F7F9 content area on a
 * 12-column / 24px-gutter grid with 32px padding. Only the children change
 * between the platform's screens.
 *
 * This is a REFERENCE shell, deliberately separate from components/app/chrome.tsx
 * (the shipping frame). It renders static spec content — no data fetching, no
 * AppProvider — which is why /dashboard-v2 sits outside the app/app/ route group
 * and its AppChrome layout.
 *
 * The brand mark and wordmark come from the canonical components/ui/*; see
 * tests/branding-guard.test.ts, which fails any re-implementation.
 */
"use client";

import type { ReactNode } from "react";
import { LogoMark } from "@/components/ui/Logo";
import { Wordmark } from "@/components/ui/Wordmark";
import "./vq.css";

/* One 20px outline icon set at a single stroke weight, per the spec. */
const Icon = ({ d, size = 20 }: { d: string; size?: number }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.75}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className="shrink-0"
  >
    <path d={d} />
  </svg>
);

const NAV = [
  { label: "Dashboard", d: "M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10" },
  { label: "Projects", d: "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" },
  { label: "Document Center", d: "M7 3h7l5 5v13H5a1 1 0 01-1-1V4a1 1 0 011-1zM14 3v5h5M8 13h8M8 17h6" },
  { label: "AI Findings", d: "M12 3.5L13.7 9l5.5 1.7L13.7 12.4 12 18l-1.7-5.6L4.8 10.7 10.3 9z" },
  { label: "Evidence Review", d: "M17.5 11a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0zM15.8 15.8L21 21M8.4 11.1l1.9 1.9 3.4-3.4" },
  { label: "Reports", d: "M4 20V10M9.3 20V4M14.7 20v-7M20 20V8" },
  { label: "Team", d: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8" },
  { label: "Organisation", d: "M3 21h18M5 21V7l7-4 7 4v14M9 21v-4h6v4M9 10h.01M12 10h.01M15 10h.01M9 13h.01M12 13h.01M15 13h.01" },
  { label: "Settings", d: "M3.5 7h5M13 7h7.5M3.5 17h7.5M15.5 17h5M13.1 7a2.3 2.3 0 11-4.6 0 2.3 2.3 0 014.6 0zM15.5 17a2.3 2.3 0 104.6 0 2.3 2.3 0 00-4.6 0z" },
  { label: "Billing", d: "M2.5 7.5a2 2 0 012-2h15a2 2 0 012 2v9a2 2 0 01-2 2h-15a2 2 0 01-2-2v-9zM2.5 10h19M6 14.5h4" },
];

const DOCS_USED = 340;
const DOCS_LIMIT = 500;

export function VqChrome({
  title,
  subtitle,
  active = "Dashboard",
  children,
}: {
  title: string;
  subtitle: string;
  /** Which nav row reads as current. */
  active?: string;
  children: ReactNode;
}) {
  return (
    <div className="vq-root flex min-h-screen bg-vq-bg font-vq text-vq-ink">
      {/* ------------------------------------------------------- sidebar --- */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-vq-line bg-vq-card">
        <div className="flex h-[72px] items-center gap-2.5 border-b border-vq-line px-6">
          <LogoMark size={28} />
          <Wordmark height={17} className="text-vq-navy" />
        </div>

        <nav aria-label="Main" className="flex flex-col pt-4">
          {NAV.map((n) => {
            const on = n.label === active;
            return (
              <a
                key={n.label}
                href="#"
                aria-current={on ? "page" : undefined}
                className={`relative flex h-10 items-center gap-3 px-6 text-sm transition-colors ${
                  on
                    ? "bg-vq-navy/[0.06] font-medium text-vq-navy"
                    : "text-vq-ink-2 hover:bg-vq-bg hover:text-vq-ink"
                }`}
              >
                {on && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-vq-amber" />}
                <Icon d={n.d} />
                <span className="truncate">{n.label}</span>
              </a>
            );
          })}
        </nav>

        <div className="mt-auto border-t border-vq-line p-6">
          <p className="text-[12px] leading-relaxed text-vq-ink-2">
            <span className="font-medium text-vq-ink">Professional plan</span>
            <br />
            <span className="vq-num">{DOCS_USED}</span> of{" "}
            <span className="vq-num">{DOCS_LIMIT}</span> documents used this month
          </p>
          <div
            className="my-2.5 h-1 overflow-hidden rounded-sm bg-vq-line"
            role="progressbar"
            aria-valuenow={DOCS_USED}
            aria-valuemin={0}
            aria-valuemax={DOCS_LIMIT}
            aria-label="Documents used this month"
          >
            <span
              className="block h-full rounded-sm bg-vq-navy"
              style={{ width: `${(DOCS_USED / DOCS_LIMIT) * 100}%` }}
            />
          </div>
          <a href="#" className="text-[12px] font-medium text-vq-navy hover:underline">
            Upgrade
          </a>
        </div>
      </aside>

      {/* ---------------------------------------------------------- main --- */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[72px] shrink-0 items-center gap-6 border-b border-vq-line bg-vq-card px-8">
          <div className="min-w-0 flex-1">
            <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-vq-ink">
              {title}
            </h1>
            <p className="mt-0.5 text-[13px] text-vq-ink-2">{subtitle}</p>
          </div>

          <div className="relative w-80 shrink-0">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-vq-ink-2">
              <Icon d="M17.5 11a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0zM15.8 15.8L21 21" />
            </span>
            <label className="sr-only" htmlFor="vq-search">
              Search projects, findings, documents
            </label>
            <input
              id="vq-search"
              type="search"
              placeholder="Search projects, findings, documents"
              className="h-10 w-full rounded-md border border-vq-line bg-vq-bg pl-10 pr-3 text-sm text-vq-ink placeholder:text-vq-ink-2 focus:border-vq-navy focus:bg-vq-card focus:outline-none"
            />
          </div>

          <button
            type="button"
            aria-label="Notifications, 4 unread"
            className="relative grid h-10 w-10 shrink-0 place-items-center rounded-md text-vq-ink-2 transition-colors hover:bg-vq-bg hover:text-vq-ink"
          >
            <Icon d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0" />
            <span
              aria-hidden
              className="vq-num absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-lg bg-vq-low px-1 text-[10px] font-medium text-white ring-2 ring-vq-card"
            >
              4
            </span>
          </button>

          <button
            type="button"
            aria-label="Account: Daniel Mercer"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-vq-navy-fill text-[13px] font-medium text-white"
          >
            DM
          </button>
        </header>

        <main className="grid flex-1 grid-cols-12 content-start gap-6 p-8">{children}</main>
      </div>
    </div>
  );
}
