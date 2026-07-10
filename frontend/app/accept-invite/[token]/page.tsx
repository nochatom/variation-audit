"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError, InvitationPreview, getToken, setCompanyId, storeTokens } from "@/lib/api";
import { useTheme } from "@/lib/use-theme";
import { ErrorNote } from "@/components/ui";
import { LogoMark } from "@/components/ui/Logo";

type Stage =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "need-login"; preview: InvitationPreview }
  | { kind: "email-mismatch"; preview: InvitationPreview; loggedInAs: string }
  | { kind: "ready-to-accept"; preview: InvitationPreview }
  | { kind: "register"; preview: InvitationPreview }
  | { kind: "done" };

export default function AcceptInvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const [stage, setStage] = useState<Stage>({ kind: "loading" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      let preview: InvitationPreview;
      try {
        preview = await api.previewInvitation(token);
      } catch (e: any) {
        if (!cancelled) {
          setStage({
            kind: "invalid",
            message: e instanceof ApiError && e.status === 410
              ? "This invitation has expired, been revoked, or already been used."
              : "This invitation link isn't valid.",
          });
        }
        return;
      }
      if (cancelled) return;

      if (!preview.account_exists) {
        setStage({ kind: "register", preview });
        return;
      }
      if (!getToken()) {
        setStage({ kind: "need-login", preview });
        return;
      }
      try {
        const me = await api.me();
        if (cancelled) return;
        if (me.email.toLowerCase() === preview.email.toLowerCase()) {
          setStage({ kind: "ready-to-accept", preview });
        } else {
          setStage({ kind: "email-mismatch", preview, loggedInAs: me.email });
        }
      } catch {
        if (!cancelled) setStage({ kind: "need-login", preview });
      }
    }
    load();
    return () => { cancelled = true; };
  }, [token]);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.acceptInvitation(token);
      setCompanyId(res.company_id);
      setStage({ kind: "done" });
      router.replace("/app/dashboard");
    } catch (e: any) {
      setError(e.message || "Failed to accept invitation");
    } finally {
      setBusy(false);
    }
  }

  async function register(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const tok = await api.registerViaInvitation(token, password, fullName.trim() || undefined);
      storeTokens(tok);
      const me = await api.me();
      if (me.organizations[0]) setCompanyId(me.organizations[0].id);
      setStage({ kind: "done" });
      router.replace("/app/dashboard");
    } catch (e: any) {
      setError(e.message || "Failed to accept invitation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-ip-bg px-4 font-ip text-ip-ink">
      <button
        onClick={toggleTheme}
        className="absolute right-4 top-4 rounded-md p-1.5 text-ip-ink-2 hover:bg-ip-card-2"
        aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      >
        {theme === "dark" ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" /></svg>
        )}
      </button>
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-7 flex items-center gap-2.5" aria-label="VariationIQ home">
          <LogoMark size={32} />
          <div>
            <h1 className="text-[15px] font-bold tracking-tight text-ip-ink">VariationIQ</h1>
            <p className="text-[12px] text-ip-ink-3">AU construction variation recovery</p>
          </div>
        </Link>

        <div className="ip-card-lg p-6">
          {stage.kind === "loading" && (
            <p className="py-8 text-center text-sm text-ip-ink-3">Checking invitation…</p>
          )}

          {stage.kind === "invalid" && (
            <>
              <h2 className="mb-2 text-lg font-bold tracking-tight text-ip-ink">Invitation not valid</h2>
              <p className="mb-4 text-[13px] text-ip-ink-2">{stage.message}</p>
              <Link href="/login" className="btn-navy inline-block w-full text-center">Go to login</Link>
            </>
          )}

          {stage.kind === "need-login" && (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">
                Join {stage.preview.org_name}
              </h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                You already have a VariationIQ account for <span className="font-semibold text-ip-ink">{stage.preview.email}</span>.
                Log in to accept this invitation.
              </p>
              <Link href={`/login?redirect=${encodeURIComponent(`/accept-invite/${token}`)}`} className="btn-navy inline-block w-full text-center">
                Log in to accept
              </Link>
            </>
          )}

          {stage.kind === "email-mismatch" && (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">Wrong account</h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                This invitation was sent to <span className="font-semibold text-ip-ink">{stage.preview.email}</span>, but
                you&apos;re logged in as <span className="font-semibold text-ip-ink">{stage.loggedInAs}</span>.
              </p>
              <Link href={`/login?redirect=${encodeURIComponent(`/accept-invite/${token}`)}`} className="btn-navy inline-block w-full text-center">
                Log in as {stage.preview.email}
              </Link>
            </>
          )}

          {stage.kind === "ready-to-accept" && (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">
                Join {stage.preview.org_name}
              </h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                You&apos;ve been invited as a{stage.preview.role === "admin" ? "n" : ""} <span className="font-semibold text-ip-ink">{stage.preview.role}</span>.
              </p>
              {error && <ErrorNote message={error} />}
              <button onClick={accept} disabled={busy} className="btn-navy w-full">
                {busy ? "Joining…" : `Accept invitation`}
              </button>
            </>
          )}

          {stage.kind === "register" && (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">
                Join {stage.preview.org_name}
              </h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                Create your account for <span className="font-semibold text-ip-ink">{stage.preview.email}</span> to
                join as a{stage.preview.role === "admin" ? "n" : ""} {stage.preview.role}.
              </p>
              <form onSubmit={register} className="space-y-3">
                <div>
                  <label className="ip-label mb-1 block">Full name (optional)</label>
                  <input className="ip-input" value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={200} />
                </div>
                <div>
                  <label className="ip-label mb-1 block">Password</label>
                  <input
                    className="ip-input"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    minLength={8}
                    maxLength={128}
                    required
                  />
                  <p className="mt-1 text-[11px] text-ip-ink-3">At least 8 characters.</p>
                </div>
                {error && <ErrorNote message={error} />}
                <button disabled={busy} className="btn-navy w-full">
                  {busy ? "Creating account…" : "Create account & join"}
                </button>
              </form>
            </>
          )}

          {stage.kind === "done" && (
            <p className="py-8 text-center text-sm text-ip-ink-3">Redirecting…</p>
          )}
        </div>
      </div>
    </main>
  );
}
