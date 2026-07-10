/**
 * Canonical VariationIQ brand mark — the single source of truth for the
 * icon rendered in the navbar, footer, dashboard sidebar, login/auth pages,
 * and error pages. Every one of those previously rendered its own
 * hand-rolled "V" text glyph in a navy square; this replaces all of them.
 *
 * The navy square background reuses the app's existing `bg-ip-navy-fill`
 * design token (already theme-aware — see app/globals.css), so this
 * component is theme-correct for free. The glyph itself (a geometric V
 * with an AI sparkle tucked into its notch) is always white, so it needs
 * no separate light/dark variant — it works on the navy fill in either
 * theme.
 */
export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-md bg-ip-navy-fill ${className}`}
      style={{ height: size, width: size }}
    >
      <svg viewBox="0 0 100 100" width={Math.round(size * 0.6)} height={Math.round(size * 0.6)} aria-hidden="true">
        <path d="M24,24 L50,72 L76,24 L65,24 L50,52 L35,24 Z" fill="#FFFFFF" />
        <path
          d="M50,27.5 C50.975,28.475 55.525,33.025 56.5,34 C55.525,34.975 50.975,39.525 50,40.5 C49.025,39.525 44.475,34.975 43.5,34 C44.475,33.025 49.025,28.475 50,27.5 Z"
          fill="#FFFFFF"
        />
      </svg>
    </span>
  );
}
