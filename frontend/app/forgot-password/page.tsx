"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { mapAuthError } from "@/lib/auth-errors";
import { useTheme } from "@/lib/use-theme";
import { ErrorNote } from "@/components/ui";
import { LogoMark } from "@/components/ui/Logo";
import { Wordmark } from "@/components/ui/Wordmark";

export default function ForgotPasswordPage() {
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Backend always responds 204 whether or not the email exists â€” the
      // UI must not reveal that distinction either, so this branch never
      // varies on the actual lookup result.
      await api.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(mapAuthError(err, "forgot-password"));
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
        <Link href="/" className="mb-7 flex items-center gap-2.5" aria-label="Datum Break home">
          <LogoMark size={32} />
          <div>
            <h1 aria-label="Datum Break" className="flex"><Wordmark height={18} className="text-ip-ink" /></h1>
            <p className="text-[12px] text-ip-ink-3">AU construction variation recovery</p>
          </div>
        </Link>

        <div className="ip-card-lg p-6">
          {sent ? (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">Check your email</h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                If an account exists for <span className="font-semibold text-ip-ink">{email.trim()}</span>, we&apos;ve
                sent a link to reset your password. It expires in 1 hour.
              </p>
              <Link href="/login" className="btn-navy inline-block w-full text-center">Back to login</Link>
            </>
          ) : (
            <>
              <h2 className="mb-1 text-lg font-bold tracking-tight text-ip-ink">Reset your password</h2>
              <p className="mb-5 text-[13px] text-ip-ink-2">
                Enter your account email and we&apos;ll send you a link to reset your password.
              </p>
              <form onSubmit={submit} className="space-y-3">
                <div>
                  <label htmlFor="email" className="ip-label mb-1 block">Email</label>
                  <input
                    id="email"
                    className="ip-input"
                    type="email"
                    placeholder="name@company.com.au"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    maxLength={254}
                    required
                  />
                </div>
                {error && <ErrorNote message={error} />}
                <button disabled={busy} className="btn-navy w-full">
                  {busy ? "Sendingâ€¦" : "Send reset link"}
                </button>
              </form>
              <p className="mt-4 text-center text-[13px] text-ip-ink-2">
                <Link href="/login" className="font-medium text-ip-navy hover:underline">Back to login</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
