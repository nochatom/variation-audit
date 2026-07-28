"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Eye, EyeOff, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { mapAuthError } from "@/lib/auth-errors";
import { useTheme } from "@/lib/use-theme";
import { ErrorNote } from "@/components/ui";
import { LogoMark } from "@/components/ui/Logo";
import { Wordmark } from "@/components/ui/Wordmark";

export default function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setBusy(true);
    try {
      // Resetting revokes every existing session server-side, so there's no
      // auto-login here — the user logs back in fresh, everywhere.
      await api.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(mapAuthError(err, "reset-password"));
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
        <Link href="/" className="mb-7 flex items-center gap-2.5" aria-label="VariationiQ home">
          <LogoMark size={32} />
          <div>
            <h1 aria-label="VariationiQ" className="flex"><Wordmark height={18} className="text-ip-ink" /></h1>
            <p className="text-[12px] text-ip-ink-3">AU construction variation recovery</p>
          </div>
        </Link>

        <div className="ip-card-lg p-6">
          {done ? (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">Password updated</h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                Your password has been changed and all existing sessions have been signed out. Log in with your new password.
              </p>
              <Link href="/login" className="btn-navy inline-block w-full text-center">Go to login</Link>
            </>
          ) : (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">Set a new password</h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">Choose a new password for your account.</p>
              <form onSubmit={submit} className="space-y-3">
                <div>
                  <label htmlFor="password" className="ip-label mb-1 block">New password</label>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ip-ink-3" />
                    <input
                      id="password"
                      className="ip-input pl-9 pr-9"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      minLength={8}
                      maxLength={128}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-ip-ink-3 hover:text-ip-ink-2"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] text-ip-ink-3">At least 8 characters.</p>
                </div>
                <div>
                  <label htmlFor="confirm" className="ip-label mb-1 block">Confirm password</label>
                  <input
                    id="confirm"
                    className="ip-input"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    minLength={8}
                    maxLength={128}
                    required
                  />
                </div>
                {error && <ErrorNote message={error} />}
                <button disabled={busy} className="btn-navy w-full">
                  {busy ? "Updating…" : "Update password"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
