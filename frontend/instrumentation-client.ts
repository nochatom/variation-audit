// Browser runtime Sentry init. This exact filename (not sentry.client.config.ts)
// is required under Turbopack — see the withSentryConfig deprecation warning
// for the old convention.
import * as Sentry from "@sentry/nextjs";

const dsn =
  process.env.NEXT_PUBLIC_SENTRY_DSN ||
  "https://062ca873e45ee9f89035b98c4d5e8361@o4511662990819328.ingest.de.sentry.io/4511662992785488";

Sentry.init({
  dsn,
  tracesSampleRate: 1.0,
  // Session Replay, errors only — this app handles construction
  // variation-claim data meant as legal evidence, so no blanket session
  // recording (replaysSessionSampleRate: 0): only the ~60s around a
  // captured error is recorded (replaysOnErrorSampleRate: 1.0). maskAllText
  // + blockAllMedia are Sentry's own privacy-first defaults — set explicitly
  // here so that choice is visible in code, not an invisible default.
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 1.0,
  integrations: [
    Sentry.replayIntegration({
      maskAllText: true,
      blockAllMedia: true,
    }),
  ],
  // No profiling integration added — keep the client bundle and CSP surface
  // minimal until there's a concrete need for it.
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
