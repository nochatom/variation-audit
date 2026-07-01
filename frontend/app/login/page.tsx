"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, storeTokens, setCompanyId } from "@/lib/api";
import { useTheme } from "@/lib/use-theme";

export default function LoginPage() {
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const tok =
        mode === "login"
          ? await api.login(email.trim(), password)
          : await api.signup(email.trim(), password, orgName.trim());
      storeTokens(tok);
      const me = await api.me();
      if (me.organizations[0]) setCompanyId(me.organizations[0].id);
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err.message || "Failed");
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
        <div className="mb-7 flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-ip-navy-fill text-sm font-bold text-white">V</span>
          <div>
            <h1 className="text-[15px] font-bold tracking-tight text-ip-ink">VariationIQ</h1>
            <p className="text-[12px] text-ip-ink-3">AU construction variation recovery</p>
          </div>
        </div>

        <div className="ip-card-lg p-6">
          <div className="mb-5 flex gap-1 rounded-md border border-ip-line bg-ip-card p-1 text-sm">
            {(["login", "signup"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setError(null); }}
                className={`flex-1 rounded-sm py-1.5 font-semibold transition-colors ${
                  mode === m ? "bg-ip-navy-fill text-white" : "text-ip-ink-2 hover:text-ip-ink"
                }`}
              >
                {m === "login" ? "Log in" : "Sign up"}
              </button>
            ))}
          </div>

          <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">
            {mode === "login" ? "Sign in to your workspace" : "Create your workspace"}
          </h2>
          <p className="mb-5 text-[13px] text-ip-ink-2">
            {mode === "login" ? "Welcome back. Enter your details to continue." : "Set up your organization to start recovering variations."}
          </p>

          <form onSubmit={submit} className="space-y-3">
            {mode === "signup" && (
              <div>
                <label className="ip-label mb-1 block">Organization name</label>
                <input className="ip-input" placeholder="e.g. Harbourside Electrical Pty Ltd" value={orgName} onChange={(e) => setOrgName(e.target.value)} minLength={1} maxLength={200} required />
              </div>
            )}
            <div>
              <label className="ip-label mb-1 block">Email</label>
              <input className="ip-input" type="email" placeholder="name@company.com.au" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} required />
            </div>
            <div>
              <label className="ip-label mb-1 block">Password</label>
              <input
                className="ip-input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={mode === "signup" ? 8 : undefined}
                maxLength={128}
                required
              />
              {mode === "signup" && <p className="mt-1 text-[11px] text-ip-ink-3">At least 8 characters.</p>}
            </div>

            {error && (
              <p className="rounded-md border border-ip-risk/30 bg-ip-risk-bg px-3 py-2 text-sm font-medium text-ip-risk">{error}</p>
            )}

            <button disabled={busy} className="btn-navy w-full">
              {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
            </button>
          </form>
        </div>

        <div className="mt-5 text-center text-[12px] text-ip-ink-3">
          <Link href="/landing" className="hover:text-ip-ink">← Back to site</Link>
        </div>
      </div>
    </main>
  );
}
