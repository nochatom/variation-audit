// Server-side Sentry verification endpoint — intentionally throws so the
// error is picked up by instrumentation.ts's onRequestError hook. Standard
// Sentry convention: https://docs.sentry.io/platforms/javascript/guides/nextjs/
export async function GET() {
  throw new Error("Sentry Example API Route Error — this is a real error, not caught, sent to Sentry for verification");
}
