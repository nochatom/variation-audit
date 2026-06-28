import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Variation Audit",
  description: "AU construction variation recovery — review queue, value, and claims.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU">
      <body className="bg-slate-50 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
