import type { Config } from "tailwindcss";

// Two token sets share this config:
//  • dark Linear tokens (canvas/surface/ink/primary) — root layout body / global-error
//    fallback only (fixed, no toggle; each page sets its own bg via ip-* tokens)
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
        // ---- dark (root body / global-error fallback, fixed) ----
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
          orange: "rgb(var(--ip-orange) / <alpha-value>)",            // construction orange — NON-TEXT accents only (indicators, borders, tints, focus rings)
          "orange-2": "rgb(var(--ip-orange-2) / <alpha-value>)",       // orange text (adapts per theme for legibility)
          "orange-fill": "rgb(var(--ip-orange-fill) / <alpha-value>)", // solid fill for white-text buttons — stays #9e4300 in both themes
          recovery: "rgb(var(--ip-recovery) / <alpha-value>)",        // recovered margin (green text)
          "recovery-2": "rgb(var(--ip-recovery-2) / <alpha-value>)",
          risk: "rgb(var(--ip-risk) / <alpha-value>)",                // time-bar / error
          "risk-bg": "rgb(var(--ip-risk-bg) / <alpha-value>)",
          "recovery-bg": "rgb(var(--ip-recovery-bg) / <alpha-value>)", // tint behind recovery text — completes the pair risk already had
          warn: "rgb(var(--ip-warn) / <alpha-value>)",                 // middle severity, TEXT-SAFE (unlike orange) — 6.45:1 on card
          "warn-bg": "rgb(var(--ip-warn-bg) / <alpha-value>)",
        },

        // ---- "vq" = VariationiQ design reference (/dashboard-v2 only) ----
        // Resolves from custom properties scoped to `.vq-root`, NOT :root — see
        // components/v2/vq.css. A new namespace, so no existing utility changes.
        // amber is a NON-TEXT accent (indicator bars, chart fill, dark focus
        // ring): white on #F5A623 is ~2.0:1. Amber text uses `med` (#8A5D06).
        vq: {
          bg: "rgb(var(--vq-bg) / <alpha-value>)",
          card: "rgb(var(--vq-card) / <alpha-value>)",
          line: "rgb(var(--vq-line) / <alpha-value>)",
          ink: "rgb(var(--vq-ink) / <alpha-value>)",
          "ink-2": "rgb(var(--vq-ink-2) / <alpha-value>)",
          navy: "rgb(var(--vq-navy) / <alpha-value>)",            // adaptive: text/icons, lightens in dark
          "navy-fill": "rgb(var(--vq-navy-fill) / <alpha-value>)", // solid fill behind white text
          amber: "rgb(var(--vq-amber) / <alpha-value>)",
          high: "rgb(var(--vq-high) / <alpha-value>)",
          "high-bg": "rgb(var(--vq-high-bg) / <alpha-value>)",
          med: "rgb(var(--vq-med) / <alpha-value>)",
          "med-bg": "rgb(var(--vq-med-bg) / <alpha-value>)",
          low: "rgb(var(--vq-low) / <alpha-value>)",
          "low-bg": "rgb(var(--vq-low-bg) / <alpha-value>)",
        },
      },
      borderRadius: {
        xs: "4px", sm: "6px", md: "8px", lg: "12px", xl: "16px", xxl: "24px", pill: "9999px",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "SF Pro Display", "-apple-system", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        ip: ["var(--font-public-sans)", "Public Sans", "system-ui", "Segoe UI", "sans-serif"],
        // Declared via @font-face in components/v2/vq.css (self-hosted from
        // public/fonts/), so /dashboard-v2 needs no next/font entry in layout.tsx.
        vq: ['"VQ Roboto"', "Roboto", "system-ui", "Segoe UI", "sans-serif"],
      },
      letterSpacing: { tighter: "-0.02em", tightest: "-0.04em", display: "-0.025em" },
      boxShadow: {
        // Layered, low-opacity depth (Stripe/Linear register) — a hairline
        // ambient layer + a soft directional layer reads more premium than a
        // single flat drop shadow.
        "ip-card": "0 1px 2px 0 rgb(16 24 40 / 0.04), 0 1px 3px 0 rgb(16 24 40 / 0.03)",
        "ip-card-hover": "0 2px 6px -1px rgb(16 24 40 / 0.06), 0 6px 16px -3px rgb(16 24 40 / 0.10)",
        "ip-pop": "0 12px 32px -8px rgb(16 24 40 / 0.18), 0 4px 10px -4px rgb(16 24 40 / 0.10)",
      },
    },
  },
  plugins: [],
};

export default config;
