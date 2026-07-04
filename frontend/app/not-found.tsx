import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-ip-bg px-4 font-ip text-ip-ink">
      <div className="w-full max-w-sm text-center">
        <div className="mx-auto mb-5 grid h-10 w-10 place-items-center rounded-md bg-ip-navy-fill text-base font-bold text-white">V</div>
        <div className="ip-label text-ip-ink-3">Error 404</div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-ip-ink">Page not found</h1>
        <p className="mt-2 text-sm text-ip-ink-2">The page you’re looking for doesn’t exist or has moved.</p>
        <div className="mt-6 flex justify-center gap-2">
          <Link href="/app/dashboard" className="btn-navy">Go to Dashboard</Link>
          <Link href="/login" className="btn-ghost">Go to Login</Link>
        </div>
      </div>
    </main>
  );
}
