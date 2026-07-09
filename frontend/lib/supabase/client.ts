"use client";

// Supabase is used ONLY as an additional Google-login entry point — the
// resulting Supabase session is exchanged once (app/auth/callback/
// route.ts) for this app's own access+refresh token pair, then discarded.
// createBrowserClient (not the plain @supabase/supabase-js createClient)
// stores the PKCE code_verifier in a cookie instead of localStorage, which
// is what the official Next.js App Router guide requires for the verifier
// to survive the full-page redirect to Google and back.

import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
