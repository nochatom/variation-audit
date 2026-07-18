/**
 * Canonical VariationIQ brand mark — the single source of truth for the icon
 * in the navbar, footer, dashboard sidebar, login/auth and error pages.
 *
 * The mark is the brand monogram: the high-contrast Bodoni "Q" with its
 * squared datum, rendered in white (currentColor) inside the app's existing
 * `bg-ip-navy-fill` square token (theme-aware for free). Outlined vector
 * paths, no font dependency. Source: public/brand/variationiq-appicon.svg.
 * Every call site renders through this one component — see
 * tests/branding-guard.test.ts for the regression guard.
 */
export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <span
      className={`grid shrink-0 place-items-center overflow-hidden rounded-md bg-ip-navy-fill text-white ${className}`}
      style={{ height: size, width: size }}
    >
      <svg viewBox="0 0 100 100" width={size} height={size} fill="currentColor" aria-hidden="true">
        <g transform="translate(25.83,65.73) scale(0.03333,-0.03333)"><path d="M1225 -373V-424Q1191 -428 1118 -428Q934 -428 751.5 -336.5Q569 -245 569 0Q354 72 228.0 265.5Q102 459 102 674Q102 948 288.0 1160.0Q474 1372 727 1372Q962 1372 1155.0 1167.0Q1348 962 1348 680Q1348 450 1204.0 249.0Q1060 48 850 0Q850 -218 923.5 -296.5Q997 -375 1225 -373ZM729 1321Q618 1321 525.5 1265.0Q433 1209 407.0 1083.0Q381 957 381 639Q381 423 398.0 301.5Q415 180 489.5 100.0Q564 20 725 20Q845 20 931.5 82.5Q1018 145 1043.5 284.5Q1069 424 1069 717Q1069 998 1035.5 1111.5Q1002 1225 909.5 1273.0Q817 1321 729 1321Z" fill="currentColor"/></g>
        <rect x="47.72" y="53.72" width="4.57" height="4.57" fill="currentColor"/>
      </svg>
    </span>
  );
}
