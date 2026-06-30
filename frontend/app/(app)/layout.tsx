"use client";

import { AppProvider } from "@/lib/app-context";
import { AppChrome } from "@/components/app/chrome";

export default function AppGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppProvider>
      <AppChrome>{children}</AppChrome>
    </AppProvider>
  );
}
