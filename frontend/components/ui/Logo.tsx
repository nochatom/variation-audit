/**
 * Canonical brand mark — the single source of truth for the icon in the
 * navbar, footer, dashboard sidebar, login/auth and error pages.
 *
 * The mark is the Breakline: two datum runs at different reduced levels joined
 * by a descending riser, terminated with staff ticks. Runs are deliberately
 * unequal (46 : 28) so it reads as a change in level rather than a stair tread,
 * and the riser descends because a breakline records a drop.
 *
 * Two cuts, switched on `size`:
 *   • primary (>= 24px) — stroke 7, butt caps, staff ticks at both ends
 *   • small   (<  24px) — stroke 10, ticks removed; at 16px the primary's
 *     stroke lands at 1.12px and the ticks close up against the runs
 *
 * Rendered as vector paths in the app's existing `bg-ip-navy-fill` square
 * (theme-aware for free) — no font dependency, no file fetch. Every call site
 * renders through this one component; see tests/branding-guard.test.ts.
 *
 * Geometry mirrors public/brand/breakline-primary.svg and breakline-small.svg,
 * which are reference copies only — nothing loads them at runtime, so a change
 * there does NOT reach the app unless the paths below change too.
 */
const SMALL_CUT_BELOW = 24;

export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  const small = size < SMALL_CUT_BELOW;
  return (
    <span
      className={`grid shrink-0 place-items-center overflow-hidden rounded-md bg-ip-navy-fill text-white ${className}`}
      style={{ height: size, width: size }}
    >
      <svg
        viewBox="0 0 100 100" width={size} height={size}
        fill="none" stroke="currentColor" strokeLinejoin="miter" strokeMiterlimit={10}
        aria-hidden="true"
      >
        {small ? (
          <path d="M12 30 H59 V70 H88" strokeWidth={10} strokeLinecap="square" />
        ) : (
          <g strokeWidth={7} strokeLinecap="butt">
            <path d="M13 30 H59 V70 H87" />
            <path d="M13 20 V40" />
            <path d="M87 60 V80" />
          </g>
        )}
      </svg>
    </span>
  );
}
