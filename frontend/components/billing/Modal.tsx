"use client";

import { ReactNode, useEffect, useId, useRef, useState } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// Exit-animation duration must match .animate-modal-out / .animate-backdrop-out
// in globals.css (160ms) — the component stays mounted for exactly this long
// after close is requested, so the animation can finish before unmount.
const EXIT_MS = 160;

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const [closing, setClosing] = useState(false);

  function requestClose() {
    setClosing(true);
    setTimeout(onClose, EXIT_MS);
  }

  useEffect(() => {
    closeButtonRef.current?.focus();
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        requestClose();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div
        className={`absolute inset-0 bg-ip-navy/30 ${closing ? "animate-backdrop-out" : "animate-backdrop-in"}`}
        onClick={requestClose}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        className={`relative w-full max-w-lg origin-center rounded-lg border border-ip-line bg-ip-card p-6 shadow-ip-pop ${
          closing ? "animate-modal-out" : "animate-modal-in"
        }`}
      >
        <div className="flex items-start justify-between">
          <h2 id={titleId} className="text-base font-bold text-ip-ink">{title}</h2>
          <button
            ref={closeButtonRef}
            onClick={requestClose}
            className="rounded-md p-1 text-ip-ink-3 transition-colors hover:bg-ip-card-2 hover:text-ip-ink focus:outline-none focus:ring-2 focus:ring-ip-orange active:scale-90"
            aria-label="Close"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}
