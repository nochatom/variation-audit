"use client";

import { useCallback, useEffect, useState } from "react";
import { api, MemberOut } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip, ErrorNote, Spinner, EmptyState } from "@/components/ui";

export default function TeamPage() {
  const { companyId, isAdmin, me } = useApp();
  const [members, setMembers] = useState<MemberOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!companyId || !isAdmin) return;
    setMembers(await api.orgMembers(companyId));
  }, [companyId, isAdmin]);

  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!companyId || !email) return;
    setBusy(true);
    setError(null);
    try {
      await api.addMember(companyId, email, role);
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
      <PageHeader title="Team" description="Manage members and roles for your organization." />
      {error && <ErrorNote message={error} />}

      <Card className="mb-6 p-5">
        <form onSubmit={add} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[240px] flex-1">
            <label className="ip-label mb-1 block">Invite by email</label>
            <input className="ip-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com.au" required />
          </div>
          <div>
            <label className="ip-label mb-1 block">Role</label>
            <select className="ip-input w-32" value={role} onChange={(e) => setRole(e.target.value as "admin" | "member")}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button className="btn-navy" disabled={busy}>{busy ? "Adding…" : "Add member"}</button>
        </form>
        <p className="mt-2 text-[12px] text-ip-ink-3">The person must already have a VariationIQ account to be added.</p>
      </Card>

      {!members && !error && <Spinner />}
      {members && (
        <Card className="overflow-hidden">
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
