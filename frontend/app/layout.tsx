import type { Metadata } from "next";
import { Inter, Public_Sans } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-public-sans" });

export const metadata: Metadata = {
  title: "Variation Audit",
  description: "AU construction variation recovery — review queue, value, and claims.",
};

// Applies the saved Ironclad theme (light/dark) before paint, so app/login
// pages never flash the wrong theme. Landing ignores the `dark` class entirely.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("va_theme");if(t==="dark")document.documentElement.classList.add("dark");}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-AU" className={`${inter.variable} ${publicSans.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="bg-canvas font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
