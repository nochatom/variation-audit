"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/dashboard" : "/landing");
  }, [router]);
  return <main className="grid min-h-screen place-items-center text-sm text-ink-subtle">Loading…</main>;
}
