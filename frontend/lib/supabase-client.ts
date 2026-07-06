"use client";

// Supabase is used ONLY as an additional Google-login entry point (.25) —
// the resulting Supabase session is exchanged once, server-side, for this
// app's own access+refresh token pair (see api.googleLogin) and then
// discarded. It is never used as this app's session mechanism, so no
// middleware/SSR client is needed — a plain browser client is enough.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

/** Throws if NEXT_PUBLIC_SUPABASE_URL/ANON_KEY aren't set — callers (the
 * Google button, the callback page) should only call this after the user
 * opts into Google login, not on every page load. */
export function getSupabaseClient(): SupabaseClient {
  if (client) return client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error("Google login isn't configured (missing NEXT_PUBLIC_SUPABASE_URL/ANON_KEY)");
  }
  client = createClient(url, anonKey);
  return client;
}
