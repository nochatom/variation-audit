"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, setToken, setCompanyId } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
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
          ? await api.login(email, password)
          : await api.signup(email, password, orgName);
      setToken(tok.access_token);
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
    <main className="flex min-h-screen items-center justify-center bg-ip-bg px-4 font-ip text-ip-ink">
      <div className="w-full max-w-sm">
        <div className="mb-7 flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-ip-navy text-sm font-bold text-white">V</span>
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
                  mode === m ? "bg-ip-navy text-white" : "text-ip-ink-2 hover:text-ip-ink"
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
                <input className="ip-input" placeholder="e.g. Harbourside Electrical Pty Ltd" value={orgName} onChange={(e) => setOrgName(e.target.value)} required />
              </div>
            )}
            <div>
              <label className="ip-label mb-1 block">Email</label>
              <input className="ip-input" type="email" placeholder="name@company.com.au" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="ip-label mb-1 block">Password</label>
              <input className="ip-input" type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required />
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
