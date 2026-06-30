import type { Config } from "tailwindcss";

// Two token sets share this config:
//  • dark Linear tokens (canvas/surface/ink/primary) — marketing landing + login
//  • "ip" = Ironclad Precision (light) — the enterprise application (Dashboard → Settings)
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---- dark (landing/login) ----
        canvas: "#010102",
        surface: { 1: "#0f1011", 2: "#141516", 3: "#18191a", 4: "#191a1b" },
        hairline: { DEFAULT: "#23252a", strong: "#34343a" },
        ink: { DEFAULT: "#f7f8f8", muted: "#d0d6e0", subtle: "#8a8f98", tertiary: "#62666d" },
        primary: { DEFAULT: "#5e6ad2", hover: "#828fff", focus: "#5e69d1" },
        success: "#27a644",

        // ---- Ironclad Precision (light app) ----
        ip: {
          bg: "#f7f9ff",          // surface
          card: "#ffffff",         // container-lowest
          "card-2": "#eef4ff",     // container-low
          "card-3": "#e5effe",     // container
          line: "#dfe4ee",         // subtle border
          "line-strong": "#c5c6cd", // outline-variant
          ink: "#121c27",          // on-surface
          "ink-2": "#45474d",      // on-surface-variant
          "ink-3": "#75777d",      // outline / muted label
          navy: "#051125",         // primary (steel navy)
          "navy-2": "#1b263b",     // primary-container
          "navy-3": "#3c475d",     // on-primary-fixed-variant
          orange: "#ff7a26",       // construction orange (actions + time-bar)
          "orange-2": "#9e4300",   // darker orange (hover / text on light)
          recovery: "#0a7d34",     // recovered margin (green text)
          "recovery-2": "#00a437", // recovery accent
          risk: "#ba1a1a",         // time-bar / error
          "risk-bg": "#ffdad6",
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
