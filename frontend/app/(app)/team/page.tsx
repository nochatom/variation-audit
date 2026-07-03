"use client";

import { useCallback, useEffect, useState } from "react";
import { api, InvitationOut, MemberOut } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, InfoNote, Spinner, EmptyState } from "@/components/ui";

export default function TeamPage() {
  const { companyId, isAdmin, me } = useApp();
  const [members, setMembers] = useState<MemberOut[] | null>(null);
  const [invitations, setInvitations] = useState<InvitationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [busy, setBusy] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!companyId || !isAdmin) return;
    const [m, i] = await Promise.all([api.orgMembers(companyId), api.orgInvitations(companyId)]);
    setMembers(m);
    setInvitations(i);
  }, [companyId, isAdmin]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

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
        setNotice(`Invitation created, but the email couldn't be sent to ${trimmedEmail} — use "Copy link" below to share it directly.`);
      }
      setEmail("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function changeRole(userId: string, r: "admin" | "member") {
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
      /* clipboard unavailable — link is still visible in the row */
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

  return (
    <div>
      <PageHeader title="Team" description="Manage members, roles, and invitations for your organization." />
      {error && <ErrorNote message={error} />}
      {notice && <div className="mb-4"><InfoNote>{notice}</InfoNote></div>}

      <Card className="mb-6 p-5">
        <form onSubmit={invite} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <label className="ip-label mb-1 block">Invite by email</label>
            <input className="ip-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} placeholder="name@company.com.au" required />
          </div>
          <div>
            <label className="ip-label mb-1 block">Role</label>
            <select className="ip-input w-32" value={role} onChange={(e) => setRole(e.target.value as "admin" | "member")}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button className="btn-navy" disabled={busy}>{busy ? "Sending…" : "Send invite"}</button>
        </form>
        <p className="mt-2 text-[12px] text-ip-ink-3">
          Works for anyone — they don&apos;t need an existing account. We&apos;ll email them a link to join;
          you can also copy the link directly from the pending list below.
        </p>
      </Card>

      {!invitations && !error && <Spinner />}
      {invitations && invitations.length > 0 && (
        <Card className="mb-6 overflow-hidden">
          <div className="border-b border-ip-line px-4 py-3">
            <h2 className="text-sm font-bold text-ip-ink">Pending invitations ({invitations.length})</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-ip-line">
                <th className="ip-th">Email</th>
                <th className="ip-th">Role</th>
                <th className="ip-th">Expires</th>
                <th className="ip-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr key={inv.id} className="ip-row">
                  <td className="px-4 py-3 text-sm font-semibold text-ip-ink">{inv.email}</td>
                  <td className="px-4 py-3 text-sm capitalize text-ip-ink-2">{inv.role}</td>
                  <td className="px-4 py-3 text-[12px] text-ip-ink-3">{new Date(inv.expires_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => copyLink(inv)} className="btn-ghost px-2.5 py-1 text-xs">
                        {copiedId === inv.id ? "Copied" : "Copy link"}
                      </button>
                      <button onClick={() => revoke(inv.id)} className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk hover:bg-ip-risk/20">
                        Revoke
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {!members && !error && <Spinner />}
      {members && (
        <Card className="overflow-hidden">
          <div className="border-b border-ip-line px-4 py-3">
            <h2 className="text-sm font-bold text-ip-ink">Members ({members.length})</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-ip-line">
                <th className="ip-th">Member</th>
                <th className="ip-th">Role</th>
                <th className="ip-th text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => {
                const self = m.user_id === me?.user_id;
                return (
                  <tr key={m.user_id} className="ip-row">
                    <td className="px-4 py-3">
                      <div className="text-sm font-semibold text-ip-ink">{m.email || m.user_id.slice(0, 8)}{self && <span className="ml-2"><Chip>you</Chip></span>}</div>
                      {m.full_name && <div className="text-[12px] text-ip-ink-3">{m.full_name}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <select value={m.role} onChange={(e) => changeRole(m.user_id, e.target.value as "admin" | "member")} className="rounded-md border border-ip-line-strong bg-ip-card px-2 py-1 text-sm capitalize text-ip-ink focus:border-ip-orange focus:outline-none">
                        <option value="member">member</option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => remove(m.user_id)} className="rounded-md bg-ip-risk/10 px-2.5 py-1 text-xs font-semibold text-ip-risk hover:bg-ip-risk/20">Remove</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
