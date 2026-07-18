import { ReactNode } from "react";

export const aud = (n: number | null | undefined) =>
  n == null ? "—" : "$" + Math.round(n).toLocaleString();

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" });
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-[30px] font-bold leading-[1.08] tracking-display text-ip-ink">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ip-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`ip-card ${className}`}>{children}</div>;
}

export function StatCard({
  label,
  value,
  hint,
  accent,
  size = "md",
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: "recovery" | "risk" | "navy";
  /** "md" = full dashboard metric; "sm" = compact (e.g. narrow preview grids). */
  size?: "sm" | "md";
}) {
  // A small semantic dot + typographic hierarchy replaces the old left-rail
  // accent (a rounded-card rail reads as templated) — the metric itself
  // carries the colour, which is where the eye should land.
  const dot =
    accent === "recovery" ? "bg-ip-recovery" : accent === "risk" ? "bg-ip-risk" : accent === "navy" ? "bg-ip-navy" : "bg-ip-ink-3";
  const valueColor =
    accent === "recovery" ? "text-ip-recovery" : accent === "risk" ? "text-ip-risk" : "text-ip-ink";
  const pad = size === "sm" ? "p-3.5" : "p-5";
  const valueSize = size === "sm" ? "mt-2 text-[22px]" : "mt-3 text-[32px]";
  return (
    <div className={`ip-card ${pad}`}>
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden />
        <span className="ip-label">{label}</span>
      </div>
      <div className={`${valueSize} font-bold leading-none tabular-nums tracking-display ${valueColor}`}>{value}</div>
      {hint && <div className="mt-2 text-[12px] text-ip-ink-3">{hint}</div>}
    </div>
  );
}

const CHIP: Record<string, string> = {
  neutral: "bg-ip-card-3 text-ip-ink-2",
  navy: "bg-ip-navy/10 text-ip-navy",
  recovery: "bg-ip-recovery/12 text-ip-recovery",
  risk: "bg-ip-risk/10 text-ip-risk",
  orange: "bg-ip-orange/12 text-ip-orange-2",
};

export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: keyof typeof CHIP | string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] font-semibold ${CHIP[tone] ?? CHIP.neutral}`}>
      {children}
    </span>
  );
}
// alias kept for convenience
export const Badge = Chip;

export function statusTone(status: string): string {
  if (status === "confirmed" || status === "completed" || status === "succeeded") return "recovery";
  if (status === "rejected" || status === "failed") return "risk";
  return "navy";
}

/** 5-segment confidence meter on the navy evidence scale (no status colors). */
export function ConfidenceBar({ score }: { score: number }) {
  const filled = Math.max(0, Math.min(5, Math.round((score || 0) * 5)));
  return (
    <span className="inline-flex items-center gap-2">
      <span className="inline-flex gap-0.5" aria-hidden>
        {Array.from({ length: 5 }).map((_, i) => (
          <span key={i} className={`h-3 w-1.5 rounded-[2px] ${i < filled ? "bg-ip-navy" : "bg-ip-line-strong"}`} />
        ))}
      </span>
      <span className="text-[12px] font-medium tabular-nums text-ip-ink-2">{(score ?? 0).toFixed(2)}</span>
    </span>
  );
}

export function TimeBarFlag({ risk }: { risk: boolean }) {
  // Semantic status color: red = time-bar risk (ip-risk), green = on track
  // (ip-recovery, the same token used elsewhere for positive/recovered
  // value) — reuses the existing design-system tokens so this stays
  // consistent with every other risk/positive indicator in the app.
  return risk ? (
    <span className="inline-flex items-center gap-1 font-semibold text-ip-risk">
      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor"><path d="M12 2L1 21h22L12 2zm0 6l7 12H5l7-12zm-1 3v4h2v-4h-2zm0 5v2h2v-2h-2z" /></svg>
      at risk
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 font-semibold text-ip-recovery">
      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
      on track
    </span>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="ip-card flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <div className="text-sm font-semibold text-ip-ink">{title}</div>
      {body && <div className="max-w-md text-[13px] text-ip-ink-2">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return <p className="mb-4 rounded-md border border-ip-risk/30 bg-ip-risk-bg px-3 py-2 text-sm font-medium text-ip-risk">{message}</p>;
}

export function InfoNote({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-ip-line bg-ip-card-2 px-3 py-2 text-sm text-ip-ink-2">{children}</p>;
}

export function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-ip-ink-3">
      <svg viewBox="0 0 24 24" className="h-5 w-5 animate-spin text-ip-navy" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
        <path d="M21 12a9 9 0 00-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      Loading…
    </div>
  );
}
