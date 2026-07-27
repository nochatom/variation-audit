"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, Copy, ShieldCheck, TriangleAlert, User as UserIcon } from "lucide-react";
import { api, AuditEntry, InvitationOut, MemberOut } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { useFeatures, useSeats } from "@/lib/billing/hooks";
import { PageHeader, Card, Chip, ErrorNote, InfoNote, Spinner, EmptyState, fmtDate } from "@/components/ui";

type Role = "admin" | "member";

/** What the two roles actually mean — stated once, where roles are assigned,
 *  rather than left implicit in a two-option dropdown. */
const PERMISSIONS: { label: string; admin: boolean; member: boolean }[] = [
  { label: "Review and approve variations", admin: true, member: true },
  { label: "Upload documents and run analysis", admin: true, member: true },
  { label: "Generate reports", admin: true, member: true },
  { label: "Invite, remove, and change roles", admin: true, member: false },
  { label: "Manage billing and plan", admin: true, member: false },
  { label: "View the organisation audit log", admin: true, member: false },
];

export default function TeamPage() {
  const { companyId, isAdmin, me } = useApp();
  const [members, setMembers] = useState<MemberOut[] | null>(null);
  const [invitations, setInvitations] = useState<InvitationOut[] | null>(null);
  const [activity, setActivity] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [inviting, setInviting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  const { data: seats } = useSeats(isAdmin ? companyId : null);
  const { data: features } = useFeatures(isAdmin ? companyId : null);

  const load = useCallback(async () => {
    if (!companyId || !isAdmin) return;
    const [m, i] = await Promise.all([api.orgMembers(companyId), api.orgInvitations(companyId)]);
    setMembers(m);
    setInvitations(i);
    // Audit is a plan feature — a 403 here is a plan state, not a failure,
    // so it must not surface as an error banner.
    api.auditLog(companyId, undefined, 12).then(setActivity).catch(() => setActivity(null));
  }, [companyId, isAdmin]);

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);

  const adminCount = useMemo(() => (members ?? []).filter((m) => m.role === "admin").length, [members]);
  const byId = useMemo(
    () => new Map((members ?? []).map((m) => [m.user_id, m.email || m.full_name || m.user_id.slice(0, 8)])),
    [members],
  );

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    const trimmedEmail = email.trim();
    if (!companyId || !trimmedEmail) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const inv = await api.createInvitation(companyId, trimmedEmail, role);
      if (inv.email_sent === false) {
        setNotice(
          `Invitation created, but the email couldn't be sent to ${trimmedEmail} — use "Copy link" to share it directly.`,
        );
      }
      setEmail("");
      setInviting(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(userId: string, r: Role) {
    if (!companyId) return;
    try {
      await api.setMemberRole(companyId, userId, r);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(userId: string) {
    if (!companyId) return;
    setConfirmRemove(null);
    try {
      await api.removeMember(companyId, userId);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function revoke(invitationId: string) {
    if (!companyId) return;
    try {
      await api.revokeInvitation(companyId, invitationId);
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function copyLink(inv: InvitationOut) {
    if (!inv.accept_url) return;
    try {
      await navigator.clipboard.writeText(inv.accept_url);
      setCopiedId(inv.id);
      setTimeout(() => setCopiedId((id) => (id === inv.id ? null : id)), 2000);
    } catch {
      /* clipboard unavailable — link is still reachable from the row */
    }
  }

  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="Team" description="Manage who can access your organization." />
        <EmptyState title="Admin access required" body="Only organization admins can manage team members." />
      </div>
    );
  }

  const overIncluded =
    seats && seats.included_seats != null && seats.current_seats > seats.included_seats;

  return (
    <div>
      <PageHeader
        title="Team"
        description="Who can access this organisation, and what each of them is allowed to do."
        actions={
          <button onClick={() => setInviting((v) => !v)} className="btn-orange">
            {inviting ? "Cancel" : "Invite member"}
          </button>
        }
      />

      {error && <ErrorNote message={error} />}
      {notice && <div className="mb-4"><InfoNote>{notice}</InfoNote></div>}

      {/* Adding a person can cost money — say so at the moment of adding, not
          on a billing page they may never open. */}
      {inviting && (
        <Card className="mb-6 p-5">
          <form onSubmit={invite} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1">
              <label htmlFor="invite-email" className="ip-label mb-1 block">Invite by email</label>
              <input
                id="invite-email"
                className="ip-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                maxLength={254}
                placeholder="name@company.com.au"
                required
              />
            </div>
            <div>
              <label htmlFor="invite-role" className="ip-label mb-1 block">Role</label>
              <select
                id="invite-role"
                className="ip-input w-32 capitalize"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <button className="btn-navy" disabled={busy}>{busy ? "Sending…" : "Send invite"}</button>
          </form>

          <p className="mt-3 text-[12px] text-ip-ink-3">
            They don&apos;t need an existing account — we&apos;ll email a join link, and you can copy it
            directly from the pending list.
          </p>

          {seats && seats.included_seats != null && (
            <p className="mt-2 text-[12px] text-ip-ink-2">
              Using{" "}
              <span className="font-semibold tabular-nums text-ip-ink">
                {seats.current_seats} of {seats.included_seats}
              </span>{" "}
              included seats.
              {seats.current_seats >= seats.included_seats && (
                <> The next member is billed as an additional seat.</>
              )}
            </p>
          )}
        </Card>
      )}

      {overIncluded && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-md border border-ip-orange/30 bg-ip-orange/[0.08] px-4 py-3">
          <TriangleAlert className="h-4 w-4 shrink-0 text-ip-orange-2" aria-hidden />
          <span className="flex-1 text-[13px] text-ip-ink-2">
            <span className="font-semibold text-ip-ink">
              {seats!.additional_seats} additional {seats!.additional_seats === 1 ? "seat" : "seats"}
            </span>{" "}
            beyond your plan&apos;s {seats!.included_seats} included.
          </span>
          <Link href="/app/settings/billing" className="btn-ghost">Review billing</Link>
        </div>
      )}

      {!members && !error && <Spinner />}

      {/* ---- Protagonist: the people with access. ---- */}
      {members && (
        <>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="ip-label">Members ({members.length})</h2>
            {adminCount === 1 && (
              <span className="text-[12px] text-ip-ink-3">One admin — consider a second.</span>
            )}
          </div>

          <Card className="mb-8 divide-y divide-ip-line">
            {members.map((m) => {
              const self = m.user_id === me?.user_id;
              const lastAdmin = m.role === "admin" && adminCount === 1;
              const confirming = confirmRemove === m.user_id;
              return (
                <div key={m.user_id} className="flex flex-wrap items-center gap-4 px-4 py-3.5">
                  {m.role === "admin" ? (
                    <ShieldCheck className="h-4 w-4 shrink-0 text-ip-navy" aria-hidden />
                  ) : (
                    <UserIcon className="h-4 w-4 shrink-0 text-ip-ink-3" aria-hidden />
                  )}

                  <div className="min-w-[180px] flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-semibold text-ip-ink">
                        {m.email || m.user_id.slice(0, 8)}
                      </span>
                      {self && <Chip>you</Chip>}
                    </div>
                    {m.full_name && <div className="text-[12px] text-ip-ink-3">{m.full_name}</div>}
                  </div>

                  <div>
                    <label htmlFor={`role-${m.user_id}`} className="sr-only">
                      Role for {m.email || m.user_id}
                    </label>
                    <select
                      id={`role-${m.user_id}`}
                      value={m.role}
                      disabled={lastAdmin}
                      title={lastAdmin ? "The last admin can't be demoted — promote someone else first." : undefined}
                      onChange={(e) => changeRole(m.user_id, e.target.value as Role)}
                      className="rounded-md border border-ip-line-strong bg-ip-card px-2 py-1 text-sm capitalize text-ip-ink focus:border-ip-orange focus:outline-none disabled:text-ip-ink-2"
                    >
                      <option value="member">member</option>
                      <option value="admin">admin</option>
                    </select>
                  </div>

                  {/* Two-step removal. Cutting off a colleague's access is not a
                      one-click action, and you can't remove yourself here. */}
                  <div className="flex shrink-0 items-center gap-2">
                    {confirming ? (
                      <>
                        <span className="text-[12px] font-semibold text-ip-risk">Remove?</span>
                        <button
                          onClick={() => remove(m.user_id)}
                          className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk transition-colors hover:bg-ip-risk/20"
                        >
                          Confirm
                        </button>
                        <button onClick={() => setConfirmRemove(null)} className="btn-ghost px-2.5 py-1 text-xs">
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setConfirmRemove(m.user_id)}
                        disabled={self}
                        aria-label={`Remove ${m.email || m.user_id}`}
                        title={self ? "You can't remove your own access." : undefined}
                        className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk transition-colors hover:bg-ip-risk/20 disabled:bg-ip-card-3 disabled:text-ip-ink-3"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </Card>

          {/* Roles stated once, next to where they're assigned. */}
          <h2 className="ip-label mb-3">What each role can do</h2>
          <Card className="mb-8 overflow-x-auto">
            <table className="w-full min-w-[420px]">
              <caption className="sr-only">Permissions by role</caption>
              <thead>
                <tr className="border-b border-ip-line">
                  <th scope="col" className="ip-th">Permission</th>
                  <th scope="col" className="ip-th text-center">Admin</th>
                  <th scope="col" className="ip-th text-center">Member</th>
                </tr>
              </thead>
              <tbody>
                {PERMISSIONS.map((p) => (
                  <tr key={p.label} className="ip-row">
                    <td className="px-4 py-2.5 text-[13px] text-ip-ink-2">{p.label}</td>
                    <PermCell on={p.admin} />
                    <PermCell on={p.member} />
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      {invitations && invitations.length > 0 && (
        <>
          <h2 className="ip-label mb-3">Pending invitations ({invitations.length})</h2>
          <Card className="mb-8 divide-y divide-ip-line">
            {invitations.map((inv) => {
              const days = Math.ceil((new Date(inv.expires_at).getTime() - Date.now()) / 86_400_000);
              const expiring = days <= 2;
              return (
                <div key={inv.id} className="flex flex-wrap items-center gap-4 px-4 py-3.5">
                  <div className="min-w-[180px] flex-1">
                    <div className="text-[14px] font-semibold text-ip-ink">{inv.email}</div>
                    <div className="mt-1 flex items-center gap-2">
                      <Chip tone={inv.role === "admin" ? "navy" : "neutral"}>{inv.role}</Chip>
                      <span className={`text-[12px] ${expiring ? "font-semibold text-ip-risk" : "text-ip-ink-3"}`}>
                        {days <= 0 ? "Expired" : days === 1 ? "Expires tomorrow" : `Expires in ${days} days`}
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button onClick={() => copyLink(inv)} className="btn-ghost px-2.5 py-1 text-xs">
                      {copiedId === inv.id ? (
                        <><Check className="h-3.5 w-3.5" aria-hidden />Copied</>
                      ) : (
                        <><Copy className="h-3.5 w-3.5" aria-hidden />Copy link</>
                      )}
                    </button>
                    <button
                      onClick={() => revoke(inv.id)}
                      aria-label={`Revoke invitation for ${inv.email}`}
                      className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk transition-colors hover:bg-ip-risk/20"
                    >
                      Revoke
                    </button>
                  </div>
                </div>
              );
            })}
          </Card>
        </>
      )}

      {/* Activity is plan-gated; absent data means "not on this plan", which is
          a different thing from "nothing happened" and shouldn't look alike. */}
      <h2 className="ip-label mb-3">Recent activity</h2>
      {activity && activity.length > 0 ? (
        <Card className="divide-y divide-ip-line">
          {activity.map((a) => (
            <div key={a.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-4 py-2.5">
              <span className="text-[13px] font-semibold text-ip-ink">
                {a.actor_user_id ? byId.get(a.actor_user_id) ?? "Someone" : "System"}
              </span>
              <span className="text-[13px] text-ip-ink-2">
                {a.action.replace(/[._]/g, " ")} · {a.entity_type.replace(/_/g, " ")}
              </span>
              <span className="ml-auto text-[12px] tabular-nums text-ip-ink-3">{fmtDate(a.created_at)}</span>
            </div>
          ))}
        </Card>
      ) : features && !features.audit_log ? (
        <InfoNote>
          The organisation audit log isn&apos;t included in your plan.{" "}
          <Link href="/app/settings/billing" className="font-semibold text-ip-navy hover:underline">
            View plans
          </Link>
        </InfoNote>
      ) : (
        <InfoNote>No recorded activity yet.</InfoNote>
      )}
    </div>
  );
}

function PermCell({ on }: { on: boolean }) {
  return (
    <td className="px-4 py-2.5 text-center">
      {on ? (
        <>
          <Check className="inline h-4 w-4 text-ip-recovery" aria-hidden />
          <span className="sr-only">Yes</span>
        </>
      ) : (
        <>
          <span aria-hidden className="text-ip-ink-3">—</span>
          <span className="sr-only">No</span>
        </>
      )}
    </td>
  );
}
