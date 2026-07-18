"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useApp } from "@/lib/app-context";
import { api } from "@/lib/api";
import { PageHeader, Card, Chip } from "@/components/ui";

export default function SettingsPage() {
  const { me, companyId, isAdmin, setCompany, logout } = useApp();

  return (
    <div>
      <PageHeader title="Settings" description="Your account, organizations, and session." />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-sm font-bold text-ip-ink">Account</h2>
          <div className="mt-3 space-y-2 text-sm">
            <Row k="Email" v={me?.email ?? "—"} />
            <FullNameRow />
            <Row k="User ID" v={<span className="font-mono text-[12px] text-ip-ink-3">{me?.user_id.slice(0, 8)}</span>} />
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-sm font-bold text-ip-ink">Organizations</h2>
          <ul className="mt-3 space-y-2">
            {me?.organizations.map((o) => (
              <li key={o.id} className="flex items-center justify-between rounded-md border border-ip-line px-3 py-2">
                <div>
                  <div className="text-[14px] font-semibold text-ip-ink">{o.name}</div>
                  <div className="mt-0.5"><Chip tone={o.role === "admin" ? "navy" : "neutral"}>{o.role}</Chip></div>
                </div>
                {o.id === companyId ? (
                  <Chip tone="recovery">active</Chip>
                ) : (
                  <button onClick={() => setCompany(o.id)} className="btn-ghost">Switch</button>
                )}
              </li>
            ))}
            {(!me || me.organizations.length === 0) && <li className="text-[13px] text-ip-ink-3">No organizations.</li>}
          </ul>
        </Card>
      </div>

      {isAdmin && (
        <Card className="mt-6 flex items-center justify-between p-5">
          <div>
            <h2 className="text-sm font-bold text-ip-ink">Billing &amp; subscription</h2>
            <p className="mt-1 text-[13px] text-ip-ink-2">Manage your organization&apos;s plan, usage, and payment details.</p>
          </div>
          <Link href="/app/settings/billing" className="btn-navy">Manage billing</Link>
        </Card>
      )}

      <Card className="mt-6 flex items-center justify-between p-5">
        <div>
          <h2 className="text-sm font-bold text-ip-ink">Session</h2>
          <p className="mt-1 text-[13px] text-ip-ink-2">Sign out of VariationIQ on this device.</p>
        </div>
        <button onClick={logout} className="btn-ghost">Log out</button>
      </Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-ip-line py-2 last:border-0">
      <span className="text-ip-ink-2">{k}</span>
      <span className="text-ip-ink">{v}</span>
    </div>
  );
}

/** Editable "Full name" row — same layout as Row, with an inline input +
 * Save that persists via the existing PATCH /auth/me and refreshes the
 * cached user through the context's reload(). */
function FullNameRow() {
  const { me, reload } = useApp();
  const [value, setValue] = useState(me?.full_name ?? "");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");

  // Sync the field when the user loads/changes (me is null on first paint).
  useEffect(() => {
    setValue(me?.full_name ?? "");
  }, [me?.full_name]);

  const current = me?.full_name ?? "";
  const dirty = value.trim() !== current;

  async function save() {
    setSaving(true);
    setStatus("idle");
    try {
      await api.updateMe(value.trim() || null);
      await reload();
      setStatus("saved");
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b border-ip-line py-2 last:border-0">
      <span className="shrink-0 text-ip-ink-2">Full name</span>
      <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
        <input
          className="ip-input h-8 max-w-[220px] text-[13px]"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setStatus("idle");
          }}
          placeholder="Your name"
          maxLength={200}
          aria-label="Full name"
        />
        <button
          onClick={save}
          disabled={!dirty || saving}
          className="btn-navy h-8 shrink-0 px-3 text-[13px]"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
      {status === "saved" && !dirty && (
        <span className="shrink-0 text-[12px] text-ip-recovery" role="status">Saved</span>
      )}
      {status === "error" && (
        <span className="shrink-0 text-[12px] text-ip-risk" role="status">Couldn’t save</span>
      )}
    </div>
  );
}
