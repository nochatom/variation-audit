import type { Metadata } from "next";
import localFont from "next/font/local";
import { PostHogProvider } from "../lib/posthog-provider";
import "./globals.css";

// Self-hosted (see app/fonts/*.woff2) instead of next/font/google, so the
// production build never depends on fetching from Google Fonts at build time.
// Both are variable fonts (weight axis 100â€“900). CSS variable names are
// unchanged, so tailwind.config.ts (--font-inter / --font-public-sans) and
// every consumer keep working exactly as before.
const inter = localFont({
  src: "./fonts/inter.woff2",
  variable: "--font-inter",
  weight: "100 900",
  display: "swap",
});
const publicSans = localFont({
  src: "./fonts/public-sans.woff2",
  variable: "--font-public-sans",
  weight: "100 900",
  display: "swap",
});

export const metadata: Metadata = {
  title: "VariationiQ",
  description: "AU construction variation recovery â€” review queue, value, and claims.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU" className={`${inter.variable} ${publicSans.variable}`}>
      <head>
        {/* Same-origin static file (public/theme-init.js), not inline â€” lets the
            CSP use script-src 'self' with no 'unsafe-inline'. Blocking (no
            async/defer) so it still runs before paint, avoiding theme flash. */}
        <script src="/theme-init.js" />
      </head>
      <body className="bg-ip-bg font-ip text-ip-ink antialiased">
        <PostHogProvider>{children}</PostHogProvider>
      </body>
    </html>
  );
}
