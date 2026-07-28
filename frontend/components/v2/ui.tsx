/**
 * VariationiQ design-reference primitives (vq).
 *
 * Component styles for the /dashboard-v2 reference screen. These are the
 * permanent building blocks of the spec: cards, metric tiles, status pills,
 * filter chips, buttons and table cells. Every later screen composes from
 * here rather than restating the values.
 *
 * Tokens resolve from `.vq-root` (components/v2/vq.css). Nothing here reads or
 * writes the shipping app's `ip-*` system.
 */
import type { ReactNode } from "react";

/* --------------------------------------------------------------- cards --- */

/** White surface, 12px radius, 1px hairline, deliberately no drop shadow. */
export function Card({
  children,
  className = "",
  flush = false,
}: {
  children: ReactNode;
  className?: string;
  /** Drop the 24px padding — for cards whose own header/table own their insets. */
  flush?: boolean;
}) {
  return (
    <section
      className={`rounded-lg border border-vq-line bg-vq-card ${flush ? "" : "p-6"} ${className}`}
    >
      {children}
    </section>
  );
}

/** 18px semibold section heading. */
export function CardTitle({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="text-[18px] font-semibold tracking-[-0.01em] text-vq-ink">
      {children}
    </h2>
  );
}

/* -------------------------------------------------------------- metrics --- */

export function MetricCard({
  label,
  value,
  children,
  accent = false,
}: {
  label: string;
  value: string;
  /** The subdued change line beneath the value. */
  children: ReactNode;
  /** 3px amber left bar — carried by the single most important metric only. */
  accent?: boolean;
}) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-vq-line bg-vq-card p-6">
      {accent && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-vq-amber" />}
      <p className="vq-label">{label}</p>
      <p className="vq-num mb-1 mt-3 text-[32px] font-semibold leading-tight tracking-[-0.02em] text-vq-ink">
        {value}
      </p>
      <p className="text-[13px] text-vq-ink-2">{children}</p>
    </div>
  );
}

/* ---------------------------------------------------------- status pill --- */

export type Confidence = "high" | "med" | "low";

/** Confidence banding: high >= 85%, medium 70–84%, low below 70%. */
export function confidenceBand(pct: number): Confidence {
  if (pct >= 85) return "high";
  if (pct >= 70) return "med";
  return "low";
}

const PILL: Record<Confidence, string> = {
  high: "bg-vq-high-bg text-vq-high",
  med: "bg-vq-med-bg text-vq-med",
  low: "bg-vq-low-bg text-vq-low",
};

/**
 * Tinted chip, 6px radius. Colour is never the only carrier of meaning — the
 * percentage is always rendered, so the band survives greyscale and colour
 * blindness (WCAG 1.4.1).
 */
export function StatusPill({ band, children }: { band: Confidence; children: ReactNode }) {
  return (
    <span
      className={`vq-num inline-flex h-6 items-center rounded-sm px-2 text-[12px] font-medium ${PILL[band]}`}
    >
      {children}
    </span>
  );
}

/* --------------------------------------------------------------- chips --- */

/**
 * Filter chips are outlined-and-tinted when selected rather than navy-filled:
 * a filled row would place several solid navy blocks beside the one primary
 * button and break the single-primary rule the spec sets.
 */
export function FilterChips({
  options,
  selected,
  label,
}: {
  options: string[];
  selected: string;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2 px-6 pb-4">
      {options.map((o) => {
        const on = o === selected;
        return (
          <button
            key={o}
            type="button"
            aria-pressed={on}
            className={`inline-flex h-8 items-center rounded-md border px-3 text-[13px] transition-colors ${
              on
                ? "border-vq-navy bg-vq-navy/[0.06] font-medium text-vq-navy"
                : "border-vq-line bg-vq-card text-vq-ink-2 hover:text-vq-ink"
            }`}
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------- buttons --- */

/** 40px tall, 8px radius. `primary` is the only filled variant — one per region. */
export function Button({
  children,
  variant = "primary",
  className = "",
  ...rest
}: {
  children: ReactNode;
  variant?: "primary" | "secondary";
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base =
    "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition-colors";
  const look =
    variant === "primary"
      ? "bg-vq-navy-fill text-white hover:brightness-110"
      : "border border-vq-navy bg-vq-card text-vq-navy hover:bg-vq-navy/[0.06]";
  return (
    <button type="button" className={`${base} ${look} ${className}`} {...rest}>
      {children}
    </button>
  );
}

/** Plain navy text button — the tertiary tier. */
export function TextLink({
  children,
  className = "",
  ...rest
}: { children: ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`text-sm font-medium text-vq-navy hover:underline ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------ bar chart --- */

/** Horizontal bars in navy, with the largest value carrying the amber accent. */
export function BarChart({ rows }: { rows: { name: string; label: string; value: number }[] }) {
  const peak = Math.max(...rows.map((r) => r.value));
  return (
    <div className="mt-6 flex flex-col gap-4">
      {rows.map((r) => (
        <div key={r.name} className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[13px] text-vq-ink">{r.name}</span>
            <span className="vq-num text-[13px] font-medium text-vq-ink">{r.label}</span>
          </div>
          {/* Bars are decorative reinforcement — the figure above is the datum,
              so the track needs no separate accessible name. */}
          <div aria-hidden className="h-2 overflow-hidden rounded-sm bg-vq-bg">
            <span
              className={`block h-full rounded-sm ${r.value === peak ? "bg-vq-amber" : "bg-vq-navy"}`}
              style={{ width: `${(r.value / peak) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
