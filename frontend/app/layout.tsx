import type { Metadata } from "next";
import { Inter, Public_Sans } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-public-sans" });

export const metadata: Metadata = {
  title: "Variation Audit",
  description: "AU construction variation recovery — review queue, value, and claims.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU" className={`${inter.variable} ${publicSans.variable}`}>
      <body className="bg-canvas font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
