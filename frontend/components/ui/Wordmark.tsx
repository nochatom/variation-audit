/**
 * VariationiQ wordmark — set in the app's own brand face (Public Sans, the
 * `font-ip` family) rather than drawn as outlines.
 *
 * This replaced an outlined Bodoni Didone. The Bodoni was the last piece of the
 * retired identity: its Q was the same artwork as the old monogram, so the
 * "old logo" kept appearing at the end of the name long after the mark itself
 * became the Breakline.
 *
 * A constructed geometric wordmark matching the Breakline was tried first and
 * rejected on evidence: rendered at height 17 from an 84-unit viewBox the scale
 * is 0.2x, so ~20-unit counters land at 4px and the a/o/Q fill in solid. A
 * monolinear face with closed counters cannot hold at nav size; a text face
 * can, which is the whole reason UI type exists.
 *
 * There is no source-of-truth SVG. The text below IS the wordmark — nothing to
 * drift out of sync, which is what the old "Source of truth: public/brand/..."
 * comment promised and could not deliver.
 *
 * Size is a static class map, not an inline style: this app's CSP is
 * `style-src 'self'` with no unsafe-inline (see next.config.js), so a computed
 * style="font-size:Npx" is silently dropped by the browser. Tailwind's
 * arbitrary values compile to real classes and are unaffected — but they must
 * be literal strings for Tailwind to find them, hence the map.
 */
const SIZE_CLASS: Record<number, string> = {
  14: "text-[14px]",
  16: "text-[16px]",
  17: "text-[17px]",
  18: "text-[18px]",
  20: "text-[20px]",
  24: "text-[24px]",
  32: "text-[32px]",
};

export function Wordmark({ height = 16, className = "" }: { height?: number; className?: string }) {
  // Falls back to the nav size rather than silently rendering unstyled text if
  // a call site asks for a size that was never added above.
  const size = SIZE_CLASS[height] ?? SIZE_CLASS[17];
  return (
    <span
      className={`font-ip font-bold leading-none tracking-tighter whitespace-nowrap ${size} ${className}`}
    >
      VariationiQ
    </span>
  );
}
