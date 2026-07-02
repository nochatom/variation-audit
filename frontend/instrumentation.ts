// Server + edge runtime Sentry init (Next.js instrumentation hook, called
// once per runtime on boot). Client runtime is instrumentation-client.ts —
// Next.js loads these two entry points separately by design.
import * as Sentry from "@sentry/nextjs";

const dsn =
  process.env.NEXT_PUBLIC_SENTRY_DSN ||
  "https://062ca873e45ee9f89035b98c4d5e8361@o4511662990819328.ingest.de.sentry.io/4511662992785488";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init({
      dsn,
      // Full trace capture to start; dial down once real traffic volume is known.
      tracesSampleRate: 1.0,
    });
  }
}

// Reports errors surfaced via Next.js's server-side request lifecycle
// (route handlers, server components) that wouldn't otherwise reach a
// React error boundary.
export const onRequestError = Sentry.captureRequestError;
