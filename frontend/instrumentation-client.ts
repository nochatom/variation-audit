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
  // No session-replay/profiling integrations added — keep the client bundle
  // and CSP surface minimal until there's a concrete need for them.
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
