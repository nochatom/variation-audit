"use client";

import { useState } from "react";
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
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-primary text-sm font-bold text-white">
            V
          </span>
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight">Variation Audit</h1>
            <p className="text-[12px] text-ink-subtle">AU construction variation recovery</p>
          </div>
        </div>

        <form onSubmit={submit} className="va-panel space-y-3 p-6">
          <div className="flex gap-1 rounded-md bg-canvas p-1 text-sm">
            {(["login", "signup"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)}
                className={`flex-1 rounded-sm py-1.5 font-medium capitalize transition-colors ${
                  mode === m ? "bg-surface-2 text-ink" : "text-ink-subtle hover:text-ink"
                }`}>
                {m === "login" ? "Log in" : "Sign up"}
              </button>
            ))}
          </div>

          {mode === "signup" && (
            <input className="va-input" placeholder="Organization name"
              value={orgName} onChange={(e) => setOrgName(e.target.value)} required />
          )}
          <input className="va-input" type="email" placeholder="Email"
            value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input className="va-input" type="password" placeholder="Password"
            value={password} onChange={(e) => setPassword(e.target.value)} required />

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button disabled={busy} className="va-btn-primary w-full">
            {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
      </div>
    </main>
  );
}
