"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, Search, TriangleAlert } from "lucide-react";
import { api, OrgDashboard, ProjectOut } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState, statusTone, aud, fmtDate } from "@/components/ui";
import { ProjectActionsMenu, DeleteProjectModal } from "@/components/project-actions";

const AU_STATES = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"] as const;

/** Above this many projects a filter earns its place; below it, it's chrome. */
const SEARCH_THRESHOLD = 8;

export default function ProjectsPage() {
  const { companyId, isAdmin } = useApp();
  const [data, setData] = useState<OrgDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [tab, setTab] = useState<"active" | "archived">("active");
  const [archived, setArchived] = useState<ProjectOut[] | null>(null);
  const [lifecycleBusyId, setLifecycleBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectOut | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [query, setQuery] = useState("");

  const [name, setName] = useState("");
  const [state, setState] = useState("NSW");
  const [contract, setContract] = useState("");
  const [showScope, setShowScope] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!companyId) return;
    try {
      const [dash, arch] = await Promise.all([
        api.orgDashboard(companyId),
        api.listProjects(companyId, true),
      ]);
      setData(dash);
      setArchived(arch);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  async function archiveOne(id: string) {
    setLifecycleBusyId(id);
    try {
      await api.archiveProject(id);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function restore(id: string) {
    setLifecycleBusyId(id);
    try {
      await api.unarchiveProject(id);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLifecycleBusyId(null);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await api.deleteProject(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDeleteBusy(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!companyId || !trimmedName) return;
    setBusy(true);
    try {
      await api.createProject(companyId, trimmedName, contract || undefined, state || undefined);
      setName("");
      setContract("");
      setShowScope(false);
      setCreating(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // Same ordering thesis as the Dashboard queue: money with a deadline first,
  // then review backlog. A project list is a work order, not an alphabet.
  const active = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.projects ?? [])
      .filter((p) => !q || p.name.toLowerCase().includes(q))
      .sort(
        (a, b) =>
          b.time_bar_at_risk - a.time_bar_at_risk ||
          b.counts.pending - a.counts.pending ||
          a.name.localeCompare(b.name),
      );
  }, [data, query]);

  const archivedList = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (archived ?? []).filter((p) => !q || p.name.toLowerCase().includes(q));
  }, [archived, query]);

  const totalActive = data?.projects.length ?? 0;
  const showSearch = tab === "active" ? totalActive > SEARCH_THRESHOLD : (archived?.length ?? 0) > SEARCH_THRESHOLD;

  return (
    <div>
      <PageHeader
        title="Projects"
        description="Each project is a workspace for documents, analysis, and its review queue."
        actions={
          <button onClick={() => setCreating((v) => !v)} className="btn-orange">
            {creating ? "Cancel" : "New project"}
          </button>
        }
      />

      {error && <ErrorNote message={error} />}

      {creating && (
        <Card className="mb-6 p-5">
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label htmlFor="project-name" className="ip-label mb-1 block">Project name</label>
              <input
                id="project-name"
                className="ip-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Sydney Metro — Package 4"
                minLength={1}
                maxLength={300}
                required
              />
            </div>
            <div>
              <label htmlFor="project-state" className="ip-label mb-1 block">State</label>
              <div className="relative">
                <select
                  id="project-state"
                  className="ip-input w-28 appearance-none pr-8"
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                  required
                >
                  {AU_STATES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ip-ink-3"
                  aria-hidden
                />
              </div>
            </div>

            <button className="btn-navy" disabled={busy}>
              {busy ? "Creating…" : "Create project"}
            </button>

            {/* The scope baseline is optional and long — it shouldn't set the
                visual weight of a two-field create form. */}
            <div className="w-full">
              {!showScope ? (
                <button
                  type="button"
                  onClick={() => setShowScope(true)}
                  className="text-[12px] font-semibold text-ip-navy transition-colors hover:text-ip-navy/75"
                >
                  Add scope baseline
                </button>
              ) : (
                <>
                  <label htmlFor="project-scope" className="ip-label mb-1 block">
                    Contract / scope text
                  </label>
                  <textarea
                    id="project-scope"
                    className="ip-input"
                    rows={3}
                    value={contract}
                    onChange={(e) => setContract(e.target.value)}
                    maxLength={500000}
                    placeholder="Paste the agreed scope baseline, or upload a document later from Documents."
                  />
                </>
              )}
            </div>
          </form>
        </Card>
      )}

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div
          className="flex w-fit gap-1 rounded-md border border-ip-line bg-ip-card p-1 text-sm"
          role="tablist"
          aria-label="Project lifecycle"
        >
          {(["active", "archived"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`rounded-xs px-3.5 py-1.5 font-semibold capitalize transition-colors ${
                tab === t ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"
              }`}
            >
              {t}
              {t === "archived" && archived ? ` (${archived.length})` : ""}
            </button>
          ))}
        </div>

        {showSearch && (
          <div className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ip-ink-3"
              aria-hidden
            />
            <input
              className="ip-input pl-8"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter projects"
              aria-label="Filter projects by name"
            />
          </div>
        )}
      </div>

      {!data && !error && <Spinner />}

      {tab === "active" && data && totalActive === 0 && !creating && (
        <EmptyState
          title="No projects yet"
          body="Create a project to start ingesting documents and detecting unclaimed variations."
          action={<button onClick={() => setCreating(true)} className="btn-orange">Create project</button>}
        />
      )}

      {tab === "active" && data && totalActive > 0 && (
        <Card className="divide-y divide-ip-line">
          {active.length === 0 && (
            <div className="px-4 py-12 text-center text-[13px] text-ip-ink-2">
              No project matches “{query}”.
            </div>
          )}
          {active.map((p) => (
            <ProjectRow
              key={p.id}
              href={`/app/projects/${p.id}`}
              name={p.name}
              chips={
                <>
                  <Chip tone={statusTone(p.status)}>{p.status.replace(/_/g, " ")}</Chip>
                  {p.time_bar_at_risk > 0 && (
                    <Chip tone="risk">
                      <TriangleAlert className="h-3 w-3" aria-hidden />
                      {p.time_bar_at_risk} time-barred
                    </Chip>
                  )}
                  {p.counts.pending > 0 && <Chip tone="navy">{p.counts.pending} pending</Chip>}
                  {!p.has_contract && <Chip tone="orange">No contract</Chip>}
                </>
              }
              money={aud(p.recoverable_confirmed)}
              moneyLabel="confirmed"
              actions={
                <ProjectActionsMenu
                  project={{ archived_at: null }}
                  isAdmin={isAdmin}
                  busy={lifecycleBusyId === p.id}
                  onArchive={() => archiveOne(p.id)}
                  onRestore={() => {}}
                  onRequestDelete={() => {}}
                />
              }
            />
          ))}
        </Card>
      )}

      {tab === "archived" && archived && archived.length === 0 && (
        <EmptyState
          title="No archived projects"
          body="Archive a project to hide it from the dashboard without losing anything."
        />
      )}

      {/* Same row shape as active, muted — switching tabs must not reflow the page. */}
      {tab === "archived" && archived && archived.length > 0 && (
        <Card className="divide-y divide-ip-line">
          {archivedList.length === 0 && (
            <div className="px-4 py-12 text-center text-[13px] text-ip-ink-2">
              No project matches “{query}”.
            </div>
          )}
          {archivedList.map((p) => (
            <ProjectRow
              key={p.id}
              href={`/app/projects/${p.id}`}
              name={p.name}
              muted
              chips={
                <>
                  <Chip>archived</Chip>
                  <span className="text-[12px] text-ip-ink-3">
                    {p.state || "—"} · {fmtDate(p.archived_at)}
                  </span>
                </>
              }
              money={lifecycleBusyId === p.id ? "Restoring…" : undefined}
              actions={
                <ProjectActionsMenu
                  project={p}
                  isAdmin={isAdmin}
                  busy={lifecycleBusyId === p.id}
                  onArchive={() => {}}
                  onRestore={() => restore(p.id)}
                  onRequestDelete={() => setDeleteTarget(p)}
                />
              }
            />
          ))}
        </Card>
      )}

      {deleteTarget && (
        <DeleteProjectModal
          projectName={deleteTarget.name}
          busy={deleteBusy}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}

/**
 * Whole-row navigation via a stretched overlay link rather than wrapping the
 * row in an <a>. The actions menu is a real button, and interactive content
 * cannot legally nest inside an anchor — the previous card markup did exactly
 * that, which also meant opening the menu navigated away.
 */
function ProjectRow({
  href,
  name,
  chips,
  money,
  moneyLabel,
  actions,
  muted,
}: {
  href: string;
  name: string;
  chips: React.ReactNode;
  money?: string;
  moneyLabel?: string;
  actions: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <div className="group relative flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-ip-card-2">
      <div className="min-w-0 flex-1">
        <Link
          href={href}
          className="truncate text-[14px] font-semibold text-ip-ink outline-none after:absolute after:inset-0 after:content-[''] focus-visible:underline"
        >
          {name}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">{chips}</div>
      </div>

      {money && (
        <div className="shrink-0 text-right">
          <div
            className={`text-[14px] font-bold tabular-nums tracking-display ${
              muted ? "text-ip-ink-2" : "text-ip-ink"
            }`}
          >
            {money}
          </div>
          {moneyLabel && <div className="text-[11px] text-ip-ink-3">{moneyLabel}</div>}
        </div>
      )}

      {/* Sits above the stretched link so the menu is clickable. */}
      <div className="relative z-10 shrink-0">{actions}</div>
    </div>
  );
}
