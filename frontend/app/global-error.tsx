"use client";

// Catches errors thrown in the root layout itself — app/error.tsx is a
// sibling of layout.tsx and can't catch failures there. Next.js requires
// this file to render its own <html>/<body> since it replaces the whole
// root layout when active, so it stays intentionally minimal.
import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en-AU">
      <body className="bg-canvas font-sans text-ink antialiased">
        <main className="flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-sm text-center">
            <div className="mx-auto mb-5 grid h-10 w-10 place-items-center rounded-md bg-primary text-base font-bold text-white">V</div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">Something went wrong</h1>
            <p className="mt-2 text-sm text-ink-subtle">Please refresh the page. If this keeps happening, contact support.</p>
          </div>
        </main>
      </body>
    </html>
  );
}
