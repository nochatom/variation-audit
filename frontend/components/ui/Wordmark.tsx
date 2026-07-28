/**
 * Datum Break wordmark — constructed letterforms drawn from the Breakline
 * mark's own geometry rather than set in a typeface: one monolinear stroke
 * weight, square terminals, mitred joins, and diagonals only where a letter
 * cannot read without one.
 *
 * D is chamfered rather than boxed (a strictly orthogonal D is a rectangle and
 * reads as O), and A has a truncated apex so its terminal matches every other
 * stroke ending instead of spiking past cap height. Sidebearings are optically
 * fitted: diagonal-flanked pairs sit tighter than vertical-flanked ones.
 *
 * Stroked, not filled — unlike the retired Bodoni wordmark, so it takes
 * `stroke="currentColor"` with `fill="none"` and still inherits the surrounding
 * text colour for light/dark.
 *
 * The `height` prop keeps its original meaning (rendered SVG height in px), so
 * call sites are unchanged. Cap height is 70 of the 84-unit viewBox.
 *
 * Reference copy: public/brand/breakline-wordmark.svg — nothing loads it at
 * runtime; the paths below are what renders.
 */
const VIEW_W = 608;
const VIEW_H = 84;

export function Wordmark({ height = 16, className = "" }: { height?: number; className?: string }) {
  return (
    <svg
      viewBox="-7 -7 608 84"
      height={height}
      width={height * (VIEW_W / VIEW_H)}
      fill="none"
      stroke="currentColor"
      strokeWidth={10}
      strokeLinecap="butt"
      strokeLinejoin="miter"
      strokeMiterlimit={6}
      role="img"
      aria-label="Datum Break"
      className={className}
    >
      {/* D — chamfered bowl */}
      <g transform="translate(0,0)"><path d="M5 0 V70"/><path d="M5 5 H33 L43 15 V55 L33 65 H5"/></g>
      {/* A — truncated apex */}
      <g transform="translate(56,0)"><path d="M3 70 L20 0 H30 L47 70"/><path d="M13 46 H37"/></g>
      {/* T */}
      <g transform="translate(112,0)"><path d="M0 5 H46"/><path d="M23 5 V70"/></g>
      {/* U */}
      <g transform="translate(168,0)"><path d="M5 0 V65 H43 V0"/></g>
      {/* M */}
      <g transform="translate(228,0)"><path d="M5 70 V0 L29 40 L53 0 V70"/></g>
      {/* B */}
      <g transform="translate(316,0)"><path d="M5 0 V70"/><path d="M5 5 H41 V35 H5"/><path d="M5 35 H43 V65 H5"/></g>
      {/* R */}
      <g transform="translate(376,0)"><path d="M5 0 V70"/><path d="M5 5 H41 V35 H5"/><path d="M27 35 L46 70"/></g>
      {/* E */}
      <g transform="translate(436,0)"><path d="M5 0 V70"/><path d="M5 5 H44"/><path d="M5 35 H38"/><path d="M5 65 H44"/></g>
      {/* A */}
      <g transform="translate(488,0)"><path d="M3 70 L20 0 H30 L47 70"/><path d="M13 46 H37"/></g>
      {/* K */}
      <g transform="translate(546,0)"><path d="M5 0 V70"/><path d="M46 0 L12 37"/><path d="M19 29 L47 70"/></g>
    </svg>
  );
}
