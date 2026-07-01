import type { Config } from "tailwindcss";

// Two token sets share this config:
//  • dark Linear tokens (canvas/surface/ink/primary) — marketing landing only (fixed, no toggle)
//  • "ip" = Ironclad Precision — the enterprise application + Login/Sign Up.
//    ip-* colors resolve from CSS custom properties (see globals.css :root / .dark)
//    so the same utility classes (bg-ip-card, text-ip-ink, etc.) render light or
//    dark depending on the `dark` class on <html>, toggled by lib/use-theme.ts.
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---- dark (landing — fixed, not theme-toggled) ----
        canvas: "#010102",
        surface: { 1: "#0f1011", 2: "#141516", 3: "#18191a", 4: "#191a1b" },
        hairline: { DEFAULT: "#23252a", strong: "#34343a" },
        ink: { DEFAULT: "#f7f8f8", muted: "#d0d6e0", subtle: "#8a8f98", tertiary: "#62666d" },
        primary: { DEFAULT: "#5e6ad2", hover: "#828fff", focus: "#5e69d1" },
        success: "#27a644",

        // ---- Ironclad Precision (app + auth pages, light/dark toggle) ----
        ip: {
          bg: "rgb(var(--ip-bg) / <alpha-value>)",
          card: "rgb(var(--ip-card) / <alpha-value>)",
          "card-2": "rgb(var(--ip-card-2) / <alpha-value>)",
          "card-3": "rgb(var(--ip-card-3) / <alpha-value>)",
          line: "rgb(var(--ip-line) / <alpha-value>)",
          "line-strong": "rgb(var(--ip-line-strong) / <alpha-value>)",
          ink: "rgb(var(--ip-ink) / <alpha-value>)",
          "ink-2": "rgb(var(--ip-ink-2) / <alpha-value>)",
          "ink-3": "rgb(var(--ip-ink-3) / <alpha-value>)",
          navy: "rgb(var(--ip-navy) / <alpha-value>)",               // adaptive accent: text/icons/translucent chips — lightens in dark
          "navy-2": "rgb(var(--ip-navy-2) / <alpha-value>)",
          "navy-3": "rgb(var(--ip-navy-3) / <alpha-value>)",
          "navy-fill": "rgb(var(--ip-navy-fill) / <alpha-value>)",     // solid fill for white-text buttons/badges — stays dark-navy in both themes
          "navy-fill-2": "rgb(var(--ip-navy-fill-2) / <alpha-value>)",
          orange: "rgb(var(--ip-orange) / <alpha-value>)",            // construction orange (actions + time-bar)
          "orange-2": "rgb(var(--ip-orange-2) / <alpha-value>)",
          recovery: "rgb(var(--ip-recovery) / <alpha-value>)",        // recovered margin (green text)
          "recovery-2": "rgb(var(--ip-recovery-2) / <alpha-value>)",
          risk: "rgb(var(--ip-risk) / <alpha-value>)",                // time-bar / error
          "risk-bg": "rgb(var(--ip-risk-bg) / <alpha-value>)",
        },
      },
      borderRadius: {
        xs: "4px", sm: "6px", md: "8px", lg: "12px", xl: "16px", xxl: "24px", pill: "9999px",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "SF Pro Display", "-apple-system", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        ip: ["var(--font-public-sans)", "Public Sans", "system-ui", "Segoe UI", "sans-serif"],
      },
      letterSpacing: { tighter: "-0.02em", tightest: "-0.04em" },
      boxShadow: {
        "ip-card": "0 1px 2px rgb(16 24 40 / 0.05)",
        "ip-pop": "0 8px 24px -8px rgb(16 24 40 / 0.18)",
      },
    },
  },
  plugins: [],
};

export default config;
