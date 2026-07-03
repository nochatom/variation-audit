"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/dashboard" : "/login");
  }, [router]);
  return <main className="grid min-h-screen place-items-center bg-ip-bg font-ip text-sm text-ip-ink-3">Loading…</main>;
}
