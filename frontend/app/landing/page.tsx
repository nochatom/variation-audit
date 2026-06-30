import Link from "next/link";

export const metadata = {
  title: "VariationIQ — Recover every unclaimed variation",
  description:
    "AI revenue recovery for Australian construction. VariationIQ scans RFIs, site instructions and meeting minutes to find unclaimed variations, estimate recoverable value in AUD, and flag time-bar risk.",
};

export default function Landing() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <Backdrop />
      <Nav />

      {/* ---------------- hero ---------------- */}
      <main className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-y-16 px-6 pb-24 pt-14 lg:grid-cols-[1fr_1.12fr] lg:gap-x-12 lg:pb-32 lg:pt-24">
        <section className="relative z-10">
          <span className="inline-flex items-center gap-2 rounded-pill border border-hairline bg-surface-1/70 px-3 py-1 text-[12px] font-medium text-ink-muted backdrop-blur">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-primary/60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
            </span>
            AI revenue recovery for Australian construction
          </span>

          <h1 className="mt-6 text-[clamp(2.5rem,5.2vw,4rem)] font-semibold leading-[1.02] tracking-tightest text-ink">
            Recover every unclaimed{" "}
            <span className="bg-gradient-to-br from-[#aab1ff] via-[#7c87f2] to-primary bg-clip-text text-transparent">
              variation
            </span>{" "}
            in your construction projects.
          </h1>

          <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-ink-muted">
            VariationIQ scans your RFIs, site instructions and meeting minutes,
            surfaces the variations that were never claimed, estimates the
            recoverable value in <span className="text-ink">AUD</span>, and flags{" "}
            <span className="text-amber-400">time-bar deadlines</span> before they
            expire.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/login"
              className="group relative rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_-8px_rgba(94,106,210,0.7)] transition-all hover:bg-primary-hover hover:shadow-[0_10px_30px_-8px_rgba(94,106,210,0.85)]"
            >
              Start Free Analysis
            </Link>
            <Link
              href="#demo"
              className="rounded-lg border border-hairline bg-surface-1/70 px-5 py-2.5 text-sm font-semibold text-ink backdrop-blur transition-colors hover:border-hairline-strong hover:bg-surface-2"
            >
              View Demo
            </Link>
          </div>

          <div className="mt-12">
            <p className="va-eyebrow mb-3">Built for AU construction trades</p>
            <div className="flex flex-wrap gap-2">
              {["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering"].map((t) => (
                <span
                  key={t}
                  className="rounded-md border border-hairline bg-surface-1/60 px-2.5 py-1 text-[12px] text-ink-subtle backdrop-blur"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section id="demo" className="relative z-10">
          <ProductPreview />
        </section>
      </main>

      <HowItWorks />
      <Features />
      <Capabilities />
      <CtaBanner />
      <SiteFooter />
    </div>
  );
}

/* ---------------- shared backdrop: grid pattern + radial glows ---------------- */
function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0">
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage:
            "radial-gradient(ellipse 75% 55% at 50% 0%, #000 55%, transparent 100%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 75% 55% at 50% 0%, #000 55%, transparent 100%)",
        }}
      />
      <div className="absolute -top-40 left-1/2 h-[560px] w-[900px] -translate-x-1/2 rounded-full bg-primary/12 blur-[150px]" />
      <div className="absolute right-[-140px] top-44 h-[380px] w-[380px] rounded-full bg-primary/10 blur-[130px]" />
    </div>
  );
}

/* ---------------- sticky glass nav ---------------- */
function Nav() {
  return (
    <header className="sticky top-0 z-30 border-b border-hairline/60 bg-canvas/70 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-primary to-[#3f49b0] text-sm font-bold text-white shadow-[0_4px_12px_-4px_rgba(94,106,210,0.8)]">
            V
          </span>
          <span className="text-[15px] font-semibold tracking-tight">VariationIQ</span>
        </div>
        <nav className="hidden items-center gap-8 text-sm text-ink-subtle md:flex">
          <a href="#demo" className="transition-colors hover:text-ink">Product</a>
          <a href="#how" className="transition-colors hover:text-ink">How it works</a>
          <a href="#capabilities" className="transition-colors hover:text-ink">Capabilities</a>
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/login" className="rounded-md px-3 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink">
            Sign in
          </Link>
          <Link href="/login" className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover">
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}

/* ---------------- hero product preview: realistic app shell ---------------- */
function ProductPreview() {
  const nav = ["Dashboard", "Projects", "Review queue", "Reports", "Audit"];
  return (
    <div className="relative">
      {/* glow behind the app */}
      <div aria-hidden className="absolute -inset-x-8 -bottom-10 top-12 rounded-[32px] bg-primary/10 blur-3xl" />

      {/* gradient border frame */}
      <div className="relative rounded-2xl bg-gradient-to-b from-white/12 to-white/[0.02] p-px lift">
        <div className="overflow-hidden rounded-2xl bg-surface-1">
          {/* window chrome */}
          <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
            <div className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[#2a2c31]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#2a2c31]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#2a2c31]" />
            </div>
            <div className="rounded-md border border-hairline bg-canvas px-3 py-1 text-[11px] text-ink-subtle">
              app.variationiq.com.au
            </div>
            <div className="w-10" />
          </div>

          {/* app body */}
          <div className="flex">
            {/* sidebar */}
            <aside className="hidden w-40 shrink-0 border-r border-hairline bg-canvas/40 p-3 sm:block">
              <div className="flex items-center gap-2 px-1 pb-3">
                <span className="grid h-5 w-5 place-items-center rounded-[5px] bg-primary text-[10px] font-bold text-white">V</span>
                <span className="text-[12px] font-semibold">VariationIQ</span>
              </div>
              <nav className="space-y-0.5 text-[12px]">
                {nav.map((l, i) => (
                  <div
                    key={l}
                    className={`flex items-center gap-2 rounded-md px-2 py-1.5 ${
                      i === 0 ? "bg-surface-2 text-ink" : "text-ink-subtle"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${i === 0 ? "bg-primary" : "bg-hairline-strong"}`} />
                    {l}
                  </div>
                ))}
              </nav>
              <div className="mt-4 rounded-md border border-hairline bg-surface-1 p-2 text-[11px] leading-tight text-ink-subtle">
                <div className="text-ink-muted">Sydney Metro</div>
                Package 4 · Electrical
              </div>
            </aside>

            {/* main */}
            <div className="min-w-0 flex-1 p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[11px] text-ink-subtle">Projects / Sydney Metro</div>
                  <div className="text-sm font-semibold">Package 4 — Electrical</div>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-ink-subtle">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" /> Analysis complete
                </span>
              </div>

              {/* KPI cards */}
              <div className="grid grid-cols-3 gap-2.5">
                <Kpi label="Recoverable" value="$284,500" sub="AUD · confirmed" tone="accent" />
                <Kpi label="Variations" value="12" sub="detected" />
                <Kpi label="Time-bar risk" value="3" sub="within 14 days" tone="alert" />
              </div>

              {/* trend chart */}
              <div className="mt-2.5 rounded-lg border border-hairline bg-canvas/60 p-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[11px] text-ink-subtle">Recoverable value · last 6 scans</span>
                  <span className="text-[11px] text-success">↗ trending up</span>
                </div>
                <TrendChart />
              </div>

              {/* variations table */}
              <div className="mt-2.5 overflow-hidden rounded-lg border border-hairline">
                <div className="flex items-center justify-between border-b border-hairline bg-surface-2 px-3 py-1.5 text-[10px] uppercase tracking-[0.06em] text-ink-subtle">
                  <span>Detected variations</span>
                  <span>Value · Evidence</span>
                </div>
                <Row title="Additional GPOs beyond contract scope" band="high" score="0.86" value="$4,200" timeBar="4d" evidence="RFI-012" />
                <Row title="Latent ground conditions — extra excavation" band="medium" score="0.64" value="$12,500" evidence="RFI-031" />
                <Row title="Client-directed lobby finish upgrade" band="high" score="0.81" value="$18,000" timeBar="9d" evidence="MIN-07" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* floating glass alert card for depth */}
      <div className="absolute -bottom-5 -left-5 hidden w-60 rounded-xl glass p-3 lift lg:block">
        <div className="flex items-start gap-2.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-amber-500/15 text-sm text-amber-400">⚠</span>
          <div className="min-w-0">
            <div className="text-[12px] font-semibold text-ink">Time-bar closing in 4 days</div>
            <div className="text-[11px] text-ink-subtle">RFI-012 · notice clause 36.1 (NSW)</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: "accent" | "alert" }) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas/60 p-3">
      <div className="text-[10px] uppercase tracking-[0.06em] text-ink-subtle">{label}</div>
      <div className={`mt-1.5 text-lg font-semibold tabular-nums ${tone === "alert" ? "text-amber-400" : "text-ink"}`}>
        {value}
      </div>
      <div className="mt-0.5 text-[10px] text-ink-subtle">{sub}</div>
      {tone === "accent" && <div className="mt-2 h-0.5 w-8 rounded-full bg-primary/70" />}
    </div>
  );
}

function TrendChart() {
  return (
    <svg viewBox="0 0 320 72" preserveAspectRatio="none" className="h-16 w-full">
      <defs>
        <linearGradient id="va-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#5e6ad2" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#5e6ad2" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M0,58 C36,52 60,40 96,42 C132,44 150,28 192,24 C228,21 252,15 320,8 L320,72 L0,72 Z" fill="url(#va-area)" />
      <path
        d="M0,58 C36,52 60,40 96,42 C132,44 150,28 192,24 C228,21 252,15 320,8"
        fill="none"
        stroke="#8b93ff"
        strokeWidth="2"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Row({
  title, band, score, value, timeBar, evidence,
}: {
  title: string; band: "high" | "medium" | "low"; score: string; value: string; timeBar?: string; evidence: string;
}) {
  const dot = band === "high" ? "bg-success" : band === "medium" ? "bg-amber-400/70" : "bg-ink-subtle";
  const bandColor = band === "high" ? "text-success" : band === "medium" ? "text-ink-muted" : "text-ink-subtle";
  return (
    <div className="flex items-center justify-between gap-3 border-b border-hairline px-3 py-2.5 last:border-0">
      <div className="flex min-w-0 items-start gap-2">
        <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium text-ink">{title}</div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px]">
            <span className={bandColor}>{band} · {score}</span>
            {timeBar && (
              <span className="inline-flex items-center gap-1 rounded-pill bg-amber-500/10 px-1.5 py-0.5 font-medium text-amber-400">
                ⚠ {timeBar}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5">
        <span className="text-[13px] font-semibold tabular-nums text-ink">{value}</span>
        <span className="rounded-md border border-hairline bg-surface-2 px-1.5 py-0.5 text-[11px] text-primary-hover">
          {evidence} ↗
        </span>
      </div>
    </div>
  );
}

/* ---------------- section heading helper ---------------- */
function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-2.5">
        <span className="h-px w-7 bg-gradient-to-r from-primary to-transparent" />
        <span className="va-eyebrow">{eyebrow}</span>
      </div>
      <h2 className="mt-3 text-[clamp(1.9rem,3.6vw,2.6rem)] font-semibold tracking-tightest text-ink">{title}</h2>
    </div>
  );
}

function Divider() {
  return <div aria-hidden className="mx-auto h-px max-w-6xl bg-gradient-to-r from-transparent via-hairline to-transparent" />;
}

/* ---------------- section: how it works ---------------- */
function HowItWorks() {
  const steps = [
    { n: "01", title: "Ingest", body: "Connect your project record — RFIs, site instructions, meeting minutes and comms, by upload or CSV. VariationIQ normalises every source into one timeline." },
    { n: "02", title: "Detect", body: "AI reads the agreed contract baseline against every communication and surfaces work that was instructed or performed but never claimed." },
    { n: "03", title: "Recover", body: "Each variation arrives with a confidence score, an AUD estimate, a time-bar countdown, and evidence linked to its source — ready for your commercial team." },
  ];
  return (
    <section id="how" className="relative">
      <Divider />
      <div className="mx-auto max-w-6xl px-6 py-24">
        <SectionHeading eyebrow="How it works" title="From project records to recoverable revenue." />
        <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className="card group p-6 lift">
              <div className="flex items-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-lg border border-hairline bg-surface-2 font-mono text-sm text-primary-hover">
                  {s.n}
                </span>
                <h3 className="text-lg font-semibold tracking-tight">{s.title}</h3>
              </div>
              <p className="mt-4 text-sm leading-relaxed text-ink-muted">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: capabilities (feature cards + trades) ---------------- */
function Features() {
  const caps = [
    { title: "Multi-source ingestion", body: "RFIs, site instructions, meeting minutes and project comms — parsed and normalised, not just stored." },
    { title: "AI variation detection", body: "Finds out-of-scope and unclaimed work across the entire project record, clustered with its rationale." },
    { title: "AUD value & time-bar risk", body: "Recoverable estimates in AUD, plus Security of Payment notice deadlines flagged before they lapse." },
    { title: "Evidence-linked audit trail", body: "Every finding traces back to the exact source document, with an immutable record of each review decision." },
  ];
  const trades = ["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering", "Large builders"];
  return (
    <section id="capabilities" className="relative">
      <Divider />
      <div className="mx-auto max-w-6xl px-6 py-24">
        <SectionHeading eyebrow="Capabilities" title="A revenue-recovery engine, not another document store." />
        <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2">
          {caps.map((c) => (
            <div key={c.title} className="card p-6 lift">
              <div className="grid h-10 w-10 place-items-center rounded-lg border border-hairline bg-primary/12 text-primary-hover">◆</div>
              <h3 className="mt-4 text-base font-semibold tracking-tight">{c.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">{c.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-14">
          <p className="va-eyebrow mb-4">Built for every trade</p>
          <div className="flex flex-wrap gap-2.5">
            {trades.map((t) => (
              <span key={t} className="rounded-lg border border-hairline bg-surface-1 px-3.5 py-2 text-[13px] text-ink-muted transition-colors hover:border-hairline-strong hover:text-ink">
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: product capabilities (factual, no metrics/claims) ---------------- */
function Capabilities() {
  const items = [
    { title: "Australia-wide Security of Payment awareness", body: "Notice periods and time-bar logic account for state and territory SoP regimes." },
    { title: "Four supported document sources", body: "RFIs, site instructions, meeting minutes and project communications." },
    { title: "Every variation linked to supporting evidence", body: "Each finding traces back to the source document it was detected from." },
  ];
  return (
    <section className="relative">
      <Divider />
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="rounded-2xl border border-hairline bg-surface-1/40 p-8 sm:p-10">
          <p className="va-eyebrow mb-7">Product capabilities</p>
          <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
            {items.map((i) => (
              <div key={i.title} className="flex gap-3">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md border border-hairline bg-primary/12 text-[12px] text-primary-hover">✓</span>
                <div>
                  <div className="text-sm font-semibold text-ink">{i.title}</div>
                  <div className="mt-1.5 text-[13px] leading-relaxed text-ink-subtle">{i.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: closing CTA ---------------- */
function CtaBanner() {
  return (
    <section className="relative">
      <Divider />
      <div className="mx-auto max-w-6xl px-6 py-24">
        <div className="relative overflow-hidden rounded-2xl border border-hairline-strong bg-surface-1 p-12 text-center lift sm:p-16">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 opacity-60"
            style={{
              backgroundImage:
                "linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px)",
              backgroundSize: "36px 36px",
              maskImage: "radial-gradient(ellipse 60% 80% at 50% 50%, #000, transparent 75%)",
              WebkitMaskImage: "radial-gradient(ellipse 60% 80% at 50% 50%, #000, transparent 75%)",
            }}
          />
          <div aria-hidden className="pointer-events-none absolute -top-28 left-1/2 h-64 w-[640px] -translate-x-1/2 rounded-full bg-primary/15 blur-[120px]" />
          <h2 className="relative text-[clamp(1.9rem,3.6vw,2.8rem)] font-semibold tracking-tightest">
            Stop leaving variations unclaimed.
          </h2>
          <p className="relative mx-auto mt-4 max-w-xl text-ink-muted">
            See what your projects are owed. Run a free analysis on your own project record in minutes.
          </p>
          <div className="relative mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/login" className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_-8px_rgba(94,106,210,0.7)] transition-all hover:bg-primary-hover">
              Start Free Analysis
            </Link>
            <Link href="#demo" className="rounded-lg border border-hairline bg-surface-1 px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-hairline-strong hover:bg-surface-2">
              View Demo
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- footer ---------------- */
function SiteFooter() {
  return (
    <footer className="relative border-t border-hairline/60">
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 px-6 py-10 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2.5">
          <span className="grid h-6 w-6 place-items-center rounded-sm bg-primary text-xs font-bold text-white">V</span>
          <span className="text-sm font-semibold tracking-tight">VariationIQ</span>
          <span className="hidden text-[12px] text-ink-subtle sm:inline">· AI revenue recovery for Australian construction</span>
        </div>
        <p className="text-[12px] text-ink-tertiary">© 2026 VariationIQ · Estimates only — not legal advice.</p>
      </div>
    </footer>
  );
}
