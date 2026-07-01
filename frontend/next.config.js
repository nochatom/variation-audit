// Mirrors the fallback in lib/api.ts so the CSP's connect-src always matches
// the origin the browser will actually call.
const API_ORIGIN = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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
  `connect-src 'self' ${API_ORIGIN}`,
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

module.exports = nextConfig;
