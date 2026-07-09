// Google login via Supabase — Route Handler, not a client page: the PKCE
// code exchange needs read/write access to the code_verifier cookie set
// before redirect, which only a server-side handler has via next/headers
// (a client component cannot read httpOnly-eligible request cookies
// directly). Exchanges the code, then hands off to a client page to bridge
// the resulting Supabase session into this app's own JWT system.
import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}/auth/callback/complete`);
    }
  }

  return NextResponse.redirect(`${origin}/login?error=google_signin_failed`);
}
