"use client";

// Google login via Supabase, step 2: app/auth/callback/route.ts has already
// exchanged the PKCE code server-side and set the Supabase session cookie.
// This page reads that session (via the same cookie-based SSR client) and
// hands its access token to this app's own backend (POST /auth/google) to
// obtain the SAME token pair email/password login already produces — from
// that point on, this page's Supabase session is never touched again; the
// existing JWT/refresh-token system takes over exactly as it does for
// email/password.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, storeTokens, setCompanyId } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

export default function AuthCallbackCompletePage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // StrictMode/dev double-invoke guard
    ran.current = true;

    (async () => {
      try {
        const supabase = createClient();
        const { data: { session } } = await supabase.auth.getSession();
        if (!session) throw new Error("no Supabase session found");

        const tok = await api.googleLogin(session.access_token);
        // Google login has no "remember me" step of its own — treated as
        // remembered, matching how most SaaS Google-login flows behave.
        storeTokens(tok, true);
        const me = await api.me();
        if (me.organizations[0]) setCompanyId(me.organizations[0].id);

        // The Supabase session itself is no longer needed once exchanged.
        await supabase.auth.signOut();
        router.replace("/app/dashboard");
      } catch (err: any) {
        setError(err.message || "Google sign-in failed");
      }
    })();
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-ip-bg px-4 font-ip text-ip-ink">
      <div className="w-full max-w-sm text-center">
        {error ? (
          <>
            <p className="text-sm font-semibold text-ip-risk">{error}</p>
            <a href="/login" className="mt-3 inline-block text-[13px] font-medium text-ip-navy hover:underline">
              Back to sign in
            </a>
          </>
        ) : (
          <p className="text-[13px] text-ip-ink-2">Completing sign-in…</p>
        )}
      </div>
    </main>
  );
}
