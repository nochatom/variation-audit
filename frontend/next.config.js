const { withSentryConfig } = require("@sentry/nextjs");

// Mirrors the fallback in lib/api.ts so the CSP's connect-src always matches
// the origin the browser will actually call.
const API_ORIGIN = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// Sentry's browser SDK submits events to this ingest host — must be in
// connect-src or the strict CSP below silently blocks error reporting.
// Mirrors the fallback baked into instrumentation(-client).ts.
const SENTRY_DSN =
  process.env.NEXT_PUBLIC_SENTRY_DSN ||
  "https://062ca873e45ee9f89035b98c4d5e8361@o4511662990819328.ingest.de.sentry.io/4511662992785488";
const SENTRY_INGEST_ORIGIN = `https://${new URL(SENTRY_DSN).host}`;

// Google login via Supabase — lib/supabase/client.ts calls Supabase
// directly from the browser (signInWithOAuth, exchangeCodeForSession), so
// its origin must be in connect-src or the strict CSP below blocks those
// fetches with "Failed to fetch".
const SUPABASE_ORIGIN = process.env.NEXT_PUBLIC_SUPABASE_URL || "";

// PostHog analytics is reverse-proxied through this same origin at /relay
// (see rewrites() below) rather than called cross-origin, so most browsers'
// ad-blocker lists (which target *.posthog.com / *.i.posthog.com) don't
// strip the requests. Because it's same-origin, connect-src/script-src need
// no PostHog-specific entry at all — 'self' already covers it. Path is
// deliberately generic ("/relay", not "/ingest" or anything analytics-shaped)
// since some ad-blocker lists also match path substrings like /track,
// /collect, /analytics regardless of domain.
const POSTHOG_INGEST_DESTINATION = "https://eu.i.posthog.com";
const POSTHOG_ASSETS_DESTINATION = "https://eu-assets.i.posthog.com";

// script-src needs 'unsafe-inline': Next.js App Router embeds its own inline
// RSC-hydration payload scripts (<script>self.__next_f.push(...)</script>) in
// every page, including statically prerendered ones. A per-request nonce
// can't be embedded in HTML generated once at build time, and forcing every
// route to render dynamically just for CSP purity isn't worth the cost here
// (verified: no nonce-based approach works without that trade-off). This is
// a known, common limitation for Next.js App Router CSPs.
//
// style-src needs it too. React renders the `style` prop as an inline style
// ATTRIBUTE, and CSP hashes/nonces do not apply to style attributes (only to
// <style> elements) — so 'self' alone silently blocks every dynamic style in
// the app. That is not cosmetic: the analysis progress bar's width={pct%},
// the Logo's height/width, and the marketing hero's staggered animationDelay
// are all computed values that cannot be static Tailwind classes. Verified in
// a real browser: without 'unsafe-inline' Chrome logs ~15 "Applying inline
// style violates ... 'style-src self'" errors per page load and drops those
// styles. (An earlier version of this comment claimed no inline styles were
// ever emitted — that was measured before those components existed.)
//
// 'unsafe-eval' is DEV-ONLY. React's development build uses eval() for
// debugging features (reconstructing callstacks across environments) and logs
// a console error on every load without it; React never uses eval() in the
// production build, so production keeps the stricter policy. Gating on
// NODE_ENV rather than adding it outright avoids paying a real security cost
// for a dev-only convenience.
const IS_DEV = process.env.NODE_ENV !== "production";

const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${IS_DEV ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src 'self' ${API_ORIGIN} ${SENTRY_INGEST_ORIGIN}${SUPABASE_ORIGIN ? ` ${SUPABASE_ORIGIN}` : ""}`,
  // Session Replay's compression runs in a Worker constructed from a blob:
  // URL (new Blob([...]) + URL.createObjectURL) — without this, CSP falls
  // back through child-src to default-src 'self', which does NOT cover
  // blob:, and Worker creation is silently blocked (Replay degrades to a
  // slower non-worker buffer rather than failing loudly). data: added
  // alongside blob: for PostHog's worker-loading path, which can use a
  // data: URI depending on bundler/version.
  "worker-src 'self' blob: data:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "upgrade-insecure-requests",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  // Ignored by browsers over plain HTTP (harmless in local dev); takes effect once served over HTTPS.
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  // PostHog reverse proxy (see lib/posthog-provider.tsx's api_host: "/relay"):
  // routes analytics through this app's own origin instead of calling
  // *.posthog.com directly, so ad-blocker lists that target PostHog's ingest
  // domains don't silently drop capture/session-replay/flag requests.
  async rewrites() {
    return [
      { source: "/relay/static/:path*", destination: `${POSTHOG_ASSETS_DESTINATION}/static/:path*` },
      { source: "/relay/:path*", destination: `${POSTHOG_INGEST_DESTINATION}/:path*` },
    ];
  },
  // Required by PostHog's reverse-proxy setup: without this, Next.js's
  // default trailing-slash redirect on /relay/decide (etc.) strips the
  // request body/method before it ever reaches the rewrite above.
  skipTrailingSlashRedirect: true,
};

module.exports = withSentryConfig(nextConfig, {
  org: "variationiq",
  project: "sentry-amethyst-flower",
  silent: true,
  // No SENTRY_AUTH_TOKEN is configured yet — explicitly disable source-map
  // upload rather than rely on the plugin's implicit skip-with-warning, so
  // this is a deliberate, visible state instead of an easily-missed log line.
  // Set SENTRY_AUTH_TOKEN (org-level, Settings -> Auth Tokens) and remove
  // this override to enable readable stack traces in production.
  sourcemaps: { disable: !process.env.SENTRY_AUTH_TOKEN },
});
