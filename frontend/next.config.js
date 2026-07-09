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

// script-src needs 'unsafe-inline': Next.js App Router embeds its own inline
// RSC-hydration payload scripts (<script>self.__next_f.push(...)</script>) in
// every page, including statically prerendered ones. A per-request nonce
// can't be embedded in HTML generated once at build time, and forcing every
// route to render dynamically just for CSP purity isn't worth the cost here
// (verified: no nonce-based approach works without that trade-off). This is
// a known, common limitation for Next.js App Router CSPs. style-src has no
// such exception — verified no inline <style> is ever emitted.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src 'self' ${API_ORIGIN} ${SENTRY_INGEST_ORIGIN}${SUPABASE_ORIGIN ? ` ${SUPABASE_ORIGIN}` : ""}`,
  // Session Replay's compression runs in a Worker constructed from a blob:
  // URL (new Blob([...]) + URL.createObjectURL) — without this, CSP falls
  // back through child-src to default-src 'self', which does NOT cover
  // blob:, and Worker creation is silently blocked (Replay degrades to a
  // slower non-worker buffer rather than failing loudly).
  "worker-src 'self' blob:",
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
