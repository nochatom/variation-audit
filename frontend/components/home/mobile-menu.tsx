"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";

/**
 * Mobile navigation for the marketing header.
 *
 * The marketing pages are otherwise server-rendered with no client JS, so this
 * is deliberately the only interactive island: the header previously hid every
 * nav link below `md` with no control to reveal them, which left /pricing —
 * a real route, not an anchor — unreachable from a phone.
 *
 * A CSS-only <details> disclosure would have preserved the zero-JS property,
 * but it cannot close itself when a same-page anchor is followed, so tapping
 * "How it works" would scroll the page behind a menu that stayed open.
 */
export function MobileMenu({ links }: { links: { href: string; label: string }[] }) {
  const [open, setOpen] = useState(false);

  // Escape closes, and the page behind must not scroll while the panel is over it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="mobile-nav"
        aria-label={open ? "Close menu" : "Open menu"}
        // 44px square: every target in the old header was 20–32px.
        className="-mr-2 grid h-11 w-11 place-items-center rounded-md text-ip-ink-2 transition-colors hover:bg-ip-card-2 hover:text-ip-ink"
      >
        {open ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
      </button>

      {open && (
        <>
          <div
            className="fixed inset-x-0 bottom-0 top-14 z-20 bg-ip-navy/20"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div
            id="mobile-nav"
            className="fixed inset-x-0 top-14 z-30 border-b border-ip-line bg-ip-bg px-6 pb-6 pt-2 shadow-ip-pop"
          >
            <nav className="flex flex-col">
              {links.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="flex min-h-[44px] items-center border-b border-ip-line text-[15px] font-medium text-ip-ink-2 transition-colors last:border-0 hover:text-ip-ink"
                >
                  {l.label}
                </Link>
              ))}
            </nav>
            {/* Sign in, not Get started: the primary CTA stays in the header
                bar at every width, so repeating it here would be the only
                thing in the menu the user could already reach. */}
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="btn-ghost mt-5 w-full py-3 text-[15px]"
            >
              Sign in
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
