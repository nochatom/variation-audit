"use client";

import { useState } from "react";

/**
 * Per-project "⋮ More" menu — the single entry point for the project
 * lifecycle workflow (archive-first, delete-only-when-archived), used
 * identically on the Projects list and the Project Details page.
 *
 *   Active project   -> Archive
 *   Archived project -> Restore, and (admins only) Delete Permanently
 *
 * Delete Permanently never appears for an active project — the archive-first
 * safety step is enforced here in the UI AND on the server (409 if skipped).
 */
export function ProjectActionsMenu({
  project, isAdmin, busy, onArchive, onRestore, onRequestDelete,
}: {
  project: { archived_at: string | null };
  isAdmin: boolean;
  busy?: boolean;
  onArchive: () => void;
  onRestore: () => void;
  onRequestDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const archived = !!project.archived_at;

  // Stops every click inside the menu (trigger + items) from bubbling to an
  // ancestor <Link> (project list cards are entire-card links).
  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }}
        disabled={busy}
        aria-label="Project actions"
        aria-haspopup="menu"
        aria-expanded={open}
        className="grid h-7 w-7 place-items-center rounded-md text-ip-ink-2 transition-colors hover:bg-ip-card-2 hover:text-ip-ink disabled:opacity-50"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
          <circle cx="12" cy="5" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="12" cy="19" r="1.8" />
        </svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            role="menu"
            className="absolute right-0 top-8 z-40 w-52 rounded-lg border border-ip-line bg-ip-card p-1.5 shadow-ip-pop"
          >
            {!archived && (
              <MenuItem onClick={() => { setOpen(false); onArchive(); }}>
                Archive
              </MenuItem>
            )}
            {archived && (
              <>
                <MenuItem onClick={() => { setOpen(false); onRestore(); }}>
                  Restore
                </MenuItem>
                {isAdmin && (
                  <>
                    <div className="my-1 border-t border-ip-line" />
                    <MenuItem danger onClick={() => { setOpen(false); onRequestDelete(); }}>
                      Delete permanently…
                    </MenuItem>
                  </>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function MenuItem({ children, danger, onClick }: {
  children: React.ReactNode; danger?: boolean; onClick: () => void;
}) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className={`block w-full rounded-md px-3 py-2 text-left text-[13px] font-medium transition-colors ${
        danger ? "text-ip-risk hover:bg-ip-risk/10" : "text-ip-ink-2 hover:bg-ip-card-2 hover:text-ip-ink"
      }`}
    >
      {children}
    </button>
  );
}

/** Type-to-confirm modal — the required friction before an irreversible delete. */
export function DeleteProjectModal({ projectName, busy, onCancel, onConfirm }: {
  projectName: string; busy: boolean; onCancel: () => void; onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const match = typed.trim() === projectName;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ip-navy/40 px-4" onClick={onCancel}>
      <div className="ip-card-lg w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-ip-risk">Permanently delete project?</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-ip-ink-2">
          This deletes <span className="font-semibold text-ip-ink">{projectName}</span> and every
          document, analysis job, variation, evidence record and comment in it.{" "}
          <span className="font-semibold text-ip-risk">This action cannot be undone.</span>
        </p>
        <label className="ip-label mb-1 mt-4 block">Type the project name to confirm</label>
        <input className="ip-input" value={typed} onChange={(e) => setTyped(e.target.value)}
               placeholder={projectName} autoFocus />
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="btn-ghost" disabled={busy}>Cancel</button>
          <button onClick={onConfirm} disabled={!match || busy}
                  className="rounded-md bg-ip-risk px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:opacity-90 disabled:opacity-40">
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
