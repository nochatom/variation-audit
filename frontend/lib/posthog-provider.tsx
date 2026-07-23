"use client";

import { useEffect } from "react";
import posthog from "posthog-js";

// Project API key is not secret (safe to ship in the client bundle) — same
// convention as NEXT_PUBLIC_SENTRY_DSN in next.config.js: hardcoded fallback,
// optional env override for pointing at a different project per environment.
const POSTHOG_KEY =
  process.env.NEXT_PUBLIC_POSTHOG_KEY || "phc_y3DH2EhCXy7g7w2qfw7J9yMJrgkYvo5WkzkEiqFrTFas";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (posthog.__loaded) return;
    posthog.init(POSTHOG_KEY, {
      // Same-origin path, rewritten to PostHog's EU ingest/assets hosts by
      // next.config.js's rewrites() — the reverse-proxy pattern PostHog
      // recommends so ad-blockers targeting *.posthog.com don't drop
      // capture/session-replay/flag requests. ui_host keeps toolbar links
      // and the "view recording" links in captured events pointing at the
      // real PostHog app instead of this app's own origin.
      api_host: "/relay",
      ui_host: "https://eu.posthog.com",
      defaults: "2026-05-30",
      // Explicit rather than relying on `defaults` date-parsing to imply
      // these: Next.js App Router navigates via history.pushState, so a
      // route change is never a real page unload. Without SPA-aware
      // tracking, $pageleave only fires on tab close, undercounting
      // bounce rate / session duration for every in-app navigation.
      capture_pageview: "history_change",
      capture_pageleave: true,
    });
  }, []);

  return <>{children}</>;
}
