"use client";

import { useApp } from "@/lib/app-context";
import { PageHeader, Card, Chip } from "@/components/ui";

export default function SettingsPage() {
  const { me, companyId, setCompany, logout } = useApp();

  return (
    <div>
      <PageHeader title="Settings" description="Your account, organizations, and session." />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-sm font-bold text-ip-ink">Account</h2>
          <div className="mt-3 space-y-2 text-sm">
            <Row k="Email" v={me?.email ?? "—"} />
            <Row k="Full name" v={me?.full_name || "—"} />
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
