"use client";

// Sentry integration verification page — not linked from app navigation,
// reachable directly at /sentry-example-page. Exercises three capture
// paths: the client button throws in the browser (captured by
// instrumentation-client.ts's Sentry.init()); the server button hits the
// API route, which throws server-side (captured by instrumentation.ts's
// onRequestError); the metrics button sends a counter + distribution
// through the already-initialized client (Sentry.metrics, an experimental
// but functional API — see @sentry/core's metrics/public-api.ts) and
// force-flushes so delivery can be confirmed without waiting on the
// default background flush timer. Safe to leave in place — it does
// nothing unless visited directly, and every event it sends is clearly
// tagged as a verification test in Sentry.
import { useState } from "react";
import Link from "next/link";
import * as Sentry from "@sentry/nextjs";

declare function myUndefinedFunction(): void;

export default function SentryExamplePage() {
  const [serverStatus, setServerStatus] = useState<string | null>(null);
  const [metricsStatus, setMetricsStatus] = useState<string | null>(null);

  async function throwClientError() {
    // Intentionally undefined — mirrors Sentry's own documented example.
    myUndefinedFunction();
  }

  async function throwServerError() {
    setServerStatus("Calling /api/sentry-example-api…");
    try {
      const res = await fetch("/api/sentry-example-api");
      setServerStatus(`Responded ${res.status} (expected 500 — error was thrown and sent to Sentry)`);
    } catch (e: any) {
      setServerStatus(`Request failed: ${e.message}`);
    }
  }

  async function sendTestMetrics() {
    Sentry.metrics.count("verification_page.user_action", 1);
    Sentry.metrics.distribution("verification_page.api_response_time", 150, { unit: "millisecond" });
    await Sentry.flush(2000);
    setMetricsStatus("Sent counter + distribution and flushed to Sentry.");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-ip-bg px-4 font-ip text-ip-ink">
      <div className="ip-card-lg w-full max-w-md p-6 text-center">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-ip-navy-fill text-sm font-bold text-white mx-auto">V</span>
        <h1 className="mt-4 text-lg font-bold tracking-tight text-ip-ink">Sentry verification page</h1>
        <p className="mt-2 text-[13px] text-ip-ink-2">
          Not linked from navigation. Triggers a real, uncaught error on each
          side so both capture paths can be confirmed against the live
          <span className="font-semibold text-ip-ink"> sentry-amethyst-flower</span> project.
        </p>

        <div className="mt-6 flex flex-col gap-2">
          <button onClick={throwClientError} className="btn-orange">
            Throw client-side error
          </button>
          <button onClick={throwServerError} className="btn-navy">
            Throw server-side error
          </button>
          <button onClick={sendTestMetrics} className="btn-ghost">
            Send test metrics
          </button>
        </div>

        {serverStatus && (
          <p className="mt-4 rounded-md border border-ip-line bg-ip-card-2 px-3 py-2 text-[12px] text-ip-ink-2">
            {serverStatus}
          </p>
        )}
        {metricsStatus && (
          <p className="mt-2 rounded-md border border-ip-line bg-ip-card-2 px-3 py-2 text-[12px] text-ip-ink-2">
            {metricsStatus}
          </p>
        )}

        <div className="mt-6 text-[12px] text-ip-ink-3">
          <Link href="/landing" className="hover:text-ip-ink">← Back to site</Link>
        </div>
      </div>
    </main>
  );
}
