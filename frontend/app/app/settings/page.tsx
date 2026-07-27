"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Building2,
  Check,
  KeyRound,
  LogOut,
  Monitor,
  Moon,
  ScrollText,
  ShieldAlert,
  Sun,
  Users,
} from "lucide-react";
import { useApp } from "@/lib/app-context";
import { api } from "@/lib/api";
import { useTheme } from "@/lib/use-theme";
import { useUsage } from "@/lib/billing/hooks";
import { PageHeader, Card, Chip, InfoNote } from "@/components/ui";

export default function SettingsPage() {
  const { me, companyId, isAdmin, setCompany, logout } = useApp();

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Your account, this device, and how VariationIQ looks for you."
      />

      {/* ---- Protagonist: security. Everything else on this page is a
           preference; this is the part with consequences. ---- */}
      <Security email={me?.email ?? null} onLogout={logout} />

      <h2 className="ip-label mb-3 mt-8">Account</h2>
      <Card className="divide-y divide-ip-line">
        <Row k="Email" v={me?.email ?? "—"} />
        <FullNameRow />
        <Row
          k="User ID"
          v={<span className="font-mono text-[12px] text-ip-ink-3">{me?.user_id.slice(0, 8) ?? "—"}</span>}
        />
      </Card>

      <h2 className="ip-label mb-3 mt-8">Appearance</h2>
      <ThemePreference />

      <h2 className="ip-label mb-3 mt-8">Organisations</h2>
      <Card className="divide-y divide-ip-line">
        {me?.organizations.map((o) => (
          <div key={o.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-[160px] flex-1">
              <div className="text-[14px] font-semibold text-ip-ink">{o.name}</div>
              <div className="mt-1">
                <Chip tone={o.role === "admin" ? "navy" : "neutral"}>{o.role}</Chip>
              </div>
            </div>
            {o.id === companyId ? (
              <Chip tone="recovery">active</Chip>
            ) : (
              <button onClick={() => setCompany(o.id)} className="btn-ghost">
                Switch
              </button>
            )}
          </div>
        ))}
        {(!me || me.organizations.length === 0) && (
          <div className="px-4 py-6 text-[13px] text-ip-ink-3">No organisations.</div>
        )}
      </Card>

      {isAdmin && <Usage companyId={companyId} />}

      <h2 className="ip-label mb-3 mt-8">Managed elsewhere</h2>
      <Card className="divide-y divide-ip-line">
        <LinkRow
          href="/app/organisation"
          icon={<Building2 className="h-4 w-4" aria-hidden />}
          title="Organisation details"
          body="Legal entity, ABN, offices, and primary jurisdiction."
        />
        {isAdmin && (
          <LinkRow
            href="/app/team"
            icon={<Users className="h-4 w-4" aria-hidden />}
            title="Team &amp; permissions"
            body="Members, roles, invitations, and recent activity."
          />
        )}
        {isAdmin && (
          <LinkRow
            href="/app/audit"
            icon={<ScrollText className="h-4 w-4" aria-hidden />}
            title="Audit log"
            body="Every recorded change, with who made it and when."
          />
        )}
        {isAdmin && (
          <LinkRow
            href="/app/settings/billing"
            icon={<KeyRound className="h-4 w-4" aria-hidden />}
            title="Billing &amp; subscription"
            body="Plan, seats, invoices, and payment details."
          />
        )}
      </Card>

      <div className="mt-8">
        <InfoNote>
          API keys, outbound webhooks and per-event notification preferences aren&apos;t available
          yet. Notifications currently go to the in-app bell only.
        </InfoNote>
      </div>
    </div>
  );
}

/** Password + device sessions. `logoutAll` has existed in the API client since
 *  refresh tokens shipped and had no UI — this is the surface for it. */
function Security({ email, onLogout }: { email: string | null; onLogout: () => Promise<void> }) {
  const [resetSent, setResetSent] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState<"reset" | "all" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function sendReset() {
    if (!email) return;
    setBusy("reset");
    setError(null);
    try {
      await api.forgotPassword(email);
      setResetSent(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function signOutEverywhere() {
    setBusy("all");
    setError(null);
    try {
      await api.logoutAll();
      // Every refresh token is now revoked, including this device's — so the
      // only coherent next state is a local sign-out.
      await onLogout();
    } catch (e: any) {
      setError(e.message);
      setBusy(null);
      setConfirmAll(false);
    }
  }

  return (
    <section className="ip-card-lg">
      <div className="flex flex-wrap items-start gap-4 border-b border-ip-line p-6">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-ip-navy" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-[18px] font-bold tracking-display text-ip-ink">Security</h2>
          <p className="mt-1 max-w-lg text-[13px] leading-relaxed text-ip-ink-2">
            Your password and every device currently signed in to this account.
          </p>
        </div>
      </div>

      {error && (
        <p className="border-b border-ip-line bg-ip-risk-bg px-6 py-3 text-[13px] font-medium text-ip-risk">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-4 border-b border-ip-line px-6 py-4">
        <div className="min-w-[200px] flex-1">
          <div className="text-[14px] font-semibold text-ip-ink">Password</div>
          <div className="mt-0.5 text-[12px] text-ip-ink-2">
            {resetSent
              ? `Reset link sent to ${email}. It expires shortly.`
              : "We'll email you a reset link — your password is never shown or sent."}
          </div>
        </div>
        <button onClick={sendReset} disabled={busy !== null || !email} className="btn-ghost shrink-0">
          {busy === "reset" ? "Sending…" : resetSent ? <><Check className="h-3.5 w-3.5" aria-hidden />Sent</> : "Change password"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-4 px-6 py-4">
        <div className="min-w-[200px] flex-1">
          <div className="text-[14px] font-semibold text-ip-ink">Sign out everywhere</div>
          <div className="mt-0.5 text-[12px] text-ip-ink-2">
            Revokes every session on every device, including this one. Use this if a device was lost.
          </div>
        </div>
        {confirmAll ? (
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-[12px] font-semibold text-ip-risk">Sign out all devices?</span>
            <button
              onClick={signOutEverywhere}
              disabled={busy !== null}
              className="rounded-md bg-ip-risk/10 px-2.5 py-1.5 text-xs font-semibold text-ip-risk transition-colors hover:bg-ip-risk/20 disabled:opacity-50"
            >
              {busy === "all" ? "Signing out…" : "Confirm"}
            </button>
            <button onClick={() => setConfirmAll(false)} disabled={busy !== null} className="btn-ghost px-2.5 py-1.5 text-xs">
              Cancel
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirmAll(true)} className="btn-ghost shrink-0">
            Sign out all devices
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 border-t border-ip-line bg-ip-card-2 px-6 py-3">
        <span className="flex-1 text-[13px] text-ip-ink-2">Sign out of this device only.</span>
        <button onClick={onLogout} className="btn-ghost shrink-0">
          <LogOut className="h-3.5 w-3.5" aria-hidden />
          Log out
        </button>
      </div>
    </section>
  );
}

/** The dark tokens have been in globals.css all along, wired up only on the
 *  auth pages. This exposes the same hook inside the app. */
function ThemePreference() {
  const { theme, setTheme } = useTheme();
  const options = [
    { id: "light" as const, label: "Light", icon: <Sun className="h-3.5 w-3.5" aria-hidden /> },
    { id: "dark" as const, label: "Dark", icon: <Moon className="h-3.5 w-3.5" aria-hidden /> },
  ];

  return (
    <Card className="flex flex-wrap items-center gap-4 px-4 py-3.5">
      <Monitor className="h-4 w-4 shrink-0 text-ip-ink-3" aria-hidden />
      <div className="min-w-[180px] flex-1">
        <div className="text-[14px] font-semibold text-ip-ink">Theme</div>
        <div className="mt-0.5 text-[12px] text-ip-ink-3">Saved on this device only.</div>
      </div>
      <div className="flex w-fit gap-1 rounded-md border border-ip-line bg-ip-card p-1" role="group" aria-label="Theme">
        {options.map((o) => (
          <button
            key={o.id}
            aria-pressed={theme === o.id}
            onClick={() => setTheme(o.id)}
            className={`inline-flex items-center gap-1.5 rounded-xs px-3 py-1.5 text-[13px] font-semibold transition-colors ${
              theme === o.id ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"
            }`}
          >
            {o.icon}
            {o.label}
          </button>
        ))}
      </div>
    </Card>
  );
}

function Usage({ companyId }: { companyId: string | null }) {
  const { data: usage } = useUsage(companyId);
  if (!usage) return null;

  const rows = [
    { label: "Active projects", used: usage.projects_active, limit: usage.projects_limit },
    { label: "Documents processed", used: usage.documents_processed, limit: usage.documents_limit },
    { label: "Analysis runs", used: usage.analysis_runs, limit: usage.analysis_runs_limit },
  ];

  return (
    <>
      <div className="mb-3 mt-8 flex items-baseline justify-between">
        <h2 className="ip-label">Usage this period</h2>
        <span className="text-[12px] capitalize text-ip-ink-3">{usage.plan} plan</span>
      </div>
      <Card className="divide-y divide-ip-line">
        {rows.map((r) => {
          // A null limit is unlimited, not zero — treating it as a ratio would
          // report "maxed out" on the most generous plan.
          const near = r.limit != null && r.used / r.limit >= 0.8;
          return (
            <div key={r.label} className="flex flex-wrap items-center gap-4 px-4 py-3">
              <span className="min-w-[160px] flex-1 text-[13px] text-ip-ink-2">{r.label}</span>
              {/* "Near limit" is spelled out, not signalled by colour alone —
                  the count is the meter, so a bar would just re-encode it. */}
              {near && <span className="shrink-0 text-[12px] font-semibold text-ip-orange-2">Near limit</span>}
              <span
                className={`shrink-0 text-[13px] font-semibold tabular-nums ${
                  near ? "text-ip-orange-2" : "text-ip-ink"
                }`}
              >
                {r.used}
                <span className="font-normal text-ip-ink-3"> / {r.limit ?? "unlimited"}</span>
              </span>
            </div>
          );
        })}
      </Card>
    </>
  );
}

function LinkRow({
  href,
  icon,
  title,
  body,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <Link href={href} className="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-ip-card-2">
      <span className="shrink-0 text-ip-ink-3">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-semibold text-ip-ink">{title}</span>
        <span className="mt-0.5 block text-[12px] text-ip-ink-3">{body}</span>
      </span>
    </Link>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
      <span className="text-ip-ink-2">{k}</span>
      <span className="text-ip-ink">{v}</span>
    </div>
  );
}

/** Editable "Full name" row — persists via PATCH /auth/me and refreshes the
 * cached user through the context's reload(). */
function FullNameRow() {
  const { me, reload } = useApp();
  const [value, setValue] = useState(me?.full_name ?? "");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");

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
    <div className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
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
        <button onClick={save} disabled={!dirty || saving} className="btn-navy h-8 shrink-0 px-3 text-[13px]">
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
      {status === "saved" && !dirty && (
        <span className="shrink-0 text-[12px] text-ip-recovery" role="status">Saved</span>
      )}
      {status === "error" && (
        <span className="shrink-0 text-[12px] text-ip-risk" role="status">Couldn&apos;t save</span>
      )}
    </div>
  );
}
