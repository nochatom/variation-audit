"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Lock, Mail } from "lucide-react";
import { api, ApiError, storeTokens, setCompanyId, TokenResponse } from "@/lib/api";
import { mapAuthError } from "@/lib/auth-errors";
import { createClient as createSupabaseClient } from "@/lib/supabase/client";
import { useTheme } from "@/lib/use-theme";
import { ErrorNote } from "@/components/ui";
import { LogoMark } from "@/components/ui/Logo";
import { Wordmark } from "@/components/ui/Wordmark";

// Only ever follow a same-site relative path (never a scheme or "//host"
// prefix) — the redirect param is attacker-controllable query input, so an
// open redirect must be structurally impossible here, not just unlikely.
function safeRedirect(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app/dashboard";
  return raw;
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { theme, toggleTheme } = useTheme();
  // ?mode=signup opens the Sign-up tab directly. The marketing header shows
  // both "Sign in" and "Get started"; without this they resolved to the same
  // URL and the same tab, so a visitor who chose "Get started" still landed on
  // a login form and had to find the toggle themselves.
  const [mode, setMode] = useState<"login" | "signup">(
    searchParams.get("mode") === "signup" ? "signup" : "login",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const completeAuth = useCallback(
    async (tok: TokenResponse, rememberChoice: boolean) => {
      storeTokens(tok, rememberChoice);
      // tok.organizations comes straight off the login/signup response — no
      // separate GET /auth/me round trip needed just to learn this (that
      // fetch was pure duplication: AppProvider, mounted right after this
      // redirect, independently fetches /auth/me itself and already falls
      // back to organizations[0] with no companyId set — see lib/app-context.tsx).
      if (tok.organizations[0]) setCompanyId(tok.organizations[0].id);
      router.replace(safeRedirect(searchParams.get("redirect")));
    },
    [router, searchParams],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "signup") {
        // Signup is non-enumerating: it always returns a generic 202, so
        // tokens come from the follow-up login with the same credentials.
        // For a genuinely new account this logs straight in; if the email
        // already had an account, the login below fails with the same
        // "invalid credentials" any wrong password gets.
        await api.signup(email.trim(), password, orgName.trim());
      }
      const tok = await api.login(email.trim(), password);
      await completeAuth(tok, remember);
    } catch (err) {
      setError(mapAuthError(err, mode));
    } finally {
      setBusy(false);
    }
  }

  async function signInWithGoogle() {
    setError(null);
    setBusy(true);
    try {
      const supabase = createSupabaseClient();
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          // Google silently re-approves (no visible screen) once a session +
          // prior consent exist for this client — standard OAuth behavior,
          // not a bug. Forcing the account chooser here is a deliberate UX
          // choice so the user always sees/confirms which account they're
          // using, rather than the default silent-reauth fast path.
          queryParams: { prompt: "select_account" },
        },
      });
      if (oauthError) throw oauthError;
      // Browser navigates to Google now; nothing left to do here.
    } catch (err) {
      // Supabase's own client errors (popup blocked, redirect misconfigured,
      // etc.) aren't ApiError instances — mapAuthError's fallback for those
      // is generic, so give a scoped-to-Google message instead of leaking
      // the raw client error text.
      setError(err instanceof ApiError ? mapAuthError(err, "google") : "Google sign-in isn't available right now. Please try again.");
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
            <h1 aria-label="VariationIQ" className="flex"><Wordmark height={18} className="text-ip-ink" /></h1>
            <p className="text-[12px] text-ip-ink-3">AU construction variation recovery</p>
          </div>
        </Link>

        <div className="ip-card-lg p-6">
          <div className="mb-5 flex gap-1 rounded-md border border-ip-line bg-ip-card p-1 text-sm">
            {(["login", "signup"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setError(null); }}
                className={`flex-1 rounded-sm py-1.5 font-semibold transition-colors duration-150 ease-out active:scale-[0.97] ${
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
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ip-ink-3" />
                <input
                  className="ip-input pl-9"
                  type="email"
                  placeholder="name@company.com.au"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  maxLength={254}
                  required
                />
              </div>
            </div>
            <div>
              <label className="ip-label mb-1 block">Password</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ip-ink-3" />
                <input
                  className="ip-input pl-9 pr-9"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={mode === "signup" ? 8 : undefined}
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
              {mode === "signup" && <p className="mt-1 text-[11px] text-ip-ink-3">At least 8 characters.</p>}
            </div>

            <div className="flex items-center justify-between pt-0.5">
              <label className="flex items-center gap-1.5 text-[13px] text-ip-ink-2">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-ip-line-strong accent-ip-navy-fill"
                />
                Remember me
              </label>
              {mode === "login" && (
                <Link href="/forgot-password" className="text-[13px] font-medium text-ip-navy hover:underline">
                  Forgot password?
                </Link>
              )}
            </div>

            {error && <ErrorNote message={error} />}

            <button disabled={busy} className="btn-navy w-full">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="my-4 flex items-center gap-3">
            <div className="h-px flex-1 bg-ip-line" />
            <span className="text-[11px] font-medium uppercase tracking-wide text-ip-ink-3">or continue with</span>
            <div className="h-px flex-1 bg-ip-line" />
          </div>

          <button
            type="button"
            onClick={signInWithGoogle}
            disabled={busy}
            className="flex w-full items-center justify-center gap-2.5 rounded-md border border-ip-line bg-ip-card px-4 py-2 text-sm font-semibold text-ip-ink transition-[background-color,transform] duration-150 ease-out hover:bg-ip-card-2 active:scale-[0.98] disabled:opacity-60"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
              <path fill="#4285F4" d="M23.52 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.47a5.53 5.53 0 01-2.4 3.63v3.02h3.88c2.27-2.09 3.57-5.17 3.57-8.84z" />
              <path fill="#34A853" d="M12 24c3.24 0 5.96-1.07 7.95-2.9l-3.88-3.02c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.95H1.27v3.11A11.99 11.99 0 0012 24z" />
              <path fill="#FBBC05" d="M5.27 14.28A7.2 7.2 0 014.9 12c0-.79.14-1.56.37-2.28V6.61H1.27A11.99 11.99 0 000 12c0 1.94.46 3.77 1.27 5.39z" />
              <path fill="#EA4335" d="M12 4.77c1.76 0 3.34.6 4.59 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.69 1.27 6.61l4 3.11C6.22 6.88 8.87 4.77 12 4.77z" />
            </svg>
            Sign in with Google
          </button>
        </div>
      </div>
    </main>
  );
}
