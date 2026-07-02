"use client";

import { useEffect } from "react";
import Link from "next/link";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-ip-bg px-4 font-ip text-ip-ink">
      <div className="w-full max-w-sm text-center">
        <div className="mx-auto mb-5 grid h-10 w-10 place-items-center rounded-md bg-ip-navy-fill text-base font-bold text-white">V</div>
        <div className="ip-label text-ip-ink-3">Something went wrong</div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-ip-ink">Unexpected error</h1>
        <p className="mt-2 text-sm text-ip-ink-2">{error?.message || "An unexpected error occurred. Please try again."}</p>
        <div className="mt-6 flex justify-center gap-2">
          <button onClick={reset} className="btn-navy">Try again</button>
          <Link href="/dashboard" className="btn-ghost">Go to Dashboard</Link>
        </div>
      </div>
    </main>
  );
}
