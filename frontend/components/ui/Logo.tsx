/**
 * Canonical VariationIQ brand mark — the single source of truth for the
 * icon rendered in the navbar, footer, dashboard sidebar, login/auth pages,
 * and error pages.
 *
 * This is the original mark: a bold white "V" on the app's existing
 * `bg-ip-navy-fill` design token (already theme-aware — see
 * app/globals.css), so it's theme-correct for free. A separate geometric
 * SVG glyph with an AI sparkle was trialled and briefly wired in across the
 * app; it has been reverted in favor of this original mark. Every call site
 * renders it through this one component rather than re-hand-rolling the
 * span — see tests/branding-guard.test.ts for the regression guard.
 */
export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-md bg-ip-navy-fill text-sm font-bold text-white ${className}`}
      style={{ height: size, width: size }}
    >
      V
    </span>
  );
}
