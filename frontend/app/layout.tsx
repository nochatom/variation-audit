import type { Metadata } from "next";
import { Inter, Public_Sans } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-public-sans" });

export const metadata: Metadata = {
  title: "VariationIQ",
  description: "AU construction variation recovery — review queue, value, and claims.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU" className={`${inter.variable} ${publicSans.variable}`}>
      <head>
        {/* Same-origin static file (public/theme-init.js), not inline — lets the
            CSP use script-src 'self' with no 'unsafe-inline'. Blocking (no
            async/defer) so it still runs before paint, avoiding theme flash. */}
        <script src="/theme-init.js" />
      </head>
      <body className="bg-ip-bg font-ip text-ip-ink antialiased">{children}</body>
    </html>
  );
}
