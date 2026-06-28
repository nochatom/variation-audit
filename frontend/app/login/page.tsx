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
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="mb-1 text-2xl font-semibold">Variation Audit</h1>
      <p className="mb-6 text-sm text-slate-500">AU construction variation recovery</p>
      <form onSubmit={submit} className="space-y-3 rounded-xl border bg-white p-6 shadow-sm">
        <div className="flex gap-2 text-sm">
          <button type="button" onClick={() => setMode("login")}
            className={`flex-1 rounded py-1 ${mode === "login" ? "bg-slate-900 text-white" : "bg-slate-100"}`}>
            Log in
          </button>
          <button type="button" onClick={() => setMode("signup")}
            className={`flex-1 rounded py-1 ${mode === "signup" ? "bg-slate-900 text-white" : "bg-slate-100"}`}>
            Sign up
          </button>
        </div>
        {mode === "signup" && (
          <input className="w-full rounded border px-3 py-2" placeholder="Organization name"
            value={orgName} onChange={(e) => setOrgName(e.target.value)} required />
        )}
        <input className="w-full rounded border px-3 py-2" type="email" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input className="w-full rounded border px-3 py-2" type="password" placeholder="Password"
          value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button disabled={busy}
          className="w-full rounded bg-slate-900 py-2 text-white disabled:opacity-50">
          {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
    </main>
  );
}
