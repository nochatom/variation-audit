import Link from "next/link";

export const metadata = {
  title: "VariationIQ — Recover every unclaimed variation",
  description:
    "AI revenue recovery for Australian construction. VariationIQ scans RFIs, site instructions and meeting minutes to find unclaimed variations, estimate recoverable value in AUD, and flag time-bar risk.",
};

export default function Landing() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* ambient glow */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-primary/15 blur-[140px]" />
        <div className="absolute right-[-120px] top-40 h-[360px] w-[360px] rounded-full bg-primary/10 blur-[120px]" />
      </div>

      <Nav />

      <main className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-14 px-6 pb-24 pt-12 lg:grid-cols-[1.05fr_1.15fr] lg:pt-20">
        {/* ---------- left: copy ---------- */}
        <section>
          <span className="inline-flex items-center gap-2 rounded-pill border border-hairline bg-surface-1 px-3 py-1 text-[12px] font-medium text-ink-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            AI revenue recovery for Australian construction
          </span>

          <h1 className="mt-5 text-[clamp(2.4rem,5vw,3.75rem)] font-semibold leading-[1.04] tracking-tightest text-ink">
            Recover every unclaimed{" "}
            <span className="text-primary-hover">variation</span> in your
            construction projects.
          </h1>

          <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-muted">
            VariationIQ scans your RFIs, site instructions and meeting minutes,
            surfaces the variations that were never claimed, estimates the
            recoverable value in <span className="text-ink">AUD</span>, and flags
            <span className="text-amber-400"> time-bar deadlines</span> before
            they expire.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/login"
              className="rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover"
            >
              Start Free Analysis
            </Link>
            <Link
              href="#demo"
              className="rounded-md border border-hairline bg-surface-1 px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-surface-2"
            >
              View Demo
            </Link>
          </div>

          <div className="mt-10">
            <p className="va-eyebrow mb-3">Built for AU construction trades</p>
            <div className="flex flex-wrap gap-2">
              {["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering"].map(
                (t) => (
                  <span
                    key={t}
                    className="rounded-md border border-hairline bg-surface-1 px-2.5 py-1 text-[12px] text-ink-subtle"
                  >
                    {t}
                  </span>
                ),
              )}
            </div>
          </div>
        </section>

        {/* ---------- right: product mockup ---------- */}
        <section id="demo" className="relative">
          <DashboardMock />
        </section>
      </main>

      <HowItWorks />
      <Features />
      <TrustBand />
      <CtaBanner />
      <SiteFooter />
    </div>
  );
}

function Nav() {
  return (
    <header className="relative z-10 border-b border-hairline/60">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-primary text-sm font-bold text-white">
            V
          </span>
          <span className="text-[15px] font-semibold tracking-tight">VariationIQ</span>
        </div>
        <nav className="hidden items-center gap-7 text-sm text-ink-subtle md:flex">
          <a href="#demo" className="transition-colors hover:text-ink">Product</a>
          <span className="transition-colors hover:text-ink">How it works</span>
          <span className="transition-colors hover:text-ink">Pricing</span>
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

/* ---------------- dashboard mockup (HTML/CSS, looks like the live product) ---------------- */
function DashboardMock() {
  return (
    <div className="rounded-xl border border-hairline-strong bg-surface-1 shadow-2xl shadow-black/40">
      {/* window chrome */}
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
        <div className="flex items-center gap-2 text-ink-subtle">
          <span className="grid h-4 w-4 place-items-center rounded-[4px] bg-primary text-[9px] font-bold text-white">V</span>
          <span className="text-[12px] font-medium text-ink-muted">Sydney Metro · Package 4 — Electrical</span>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-ink-subtle">
          <span className="h-1.5 w-1.5 rounded-full bg-success" /> Analysis complete
        </span>
      </div>

      <div className="space-y-4 p-4">
        {/* headline metric */}
        <div className="rounded-lg border border-hairline bg-canvas p-4">
          <div className="va-eyebrow">Recoverable (confirmed)</div>
          <div className="mt-1 flex items-end gap-3">
            <span className="text-3xl font-semibold tabular-nums tracking-tight text-ink">$284,500</span>
            <span className="mb-1 text-[12px] font-medium text-success">AUD · +18% vs last scan</span>
          </div>
        </div>

        {/* stat row */}
        <div className="grid grid-cols-3 gap-3">
          <MiniStat label="Variations detected" value="12" />
          <MiniStat label="Time-bar at risk" value="3" alert />
          <MiniStat label="Avg confidence" value="82%" />
        </div>

        {/* variations table */}
        <div className="overflow-hidden rounded-lg border border-hairline">
          <div className="flex items-center justify-between border-b border-hairline bg-surface-2 px-3 py-2 text-[11px] uppercase tracking-wide text-ink-subtle">
            <span>Detected variations</span>
            <span>Value · Evidence</span>
          </div>
          <VariationRow
            title="Additional GPOs beyond contract scope"
            band="high" score="0.86" value="$4,200" timeBar="4d" evidence="RFI-012"
          />
          <VariationRow
            title="Latent ground conditions — extra excavation"
            band="medium" score="0.64" value="$12,500" evidence="RFI-031"
          />
          <VariationRow
            title="Client-directed lobby finish upgrade"
            band="high" score="0.81" value="$18,000" timeBar="9d" evidence="MIN-07"
          />
          <VariationRow
            title="Out-of-sequence switchboard rework"
            band="medium" score="0.58" value="$6,900" evidence="SI-22"
          />
        </div>

        {/* footer cards */}
        <div className="grid grid-cols-2 gap-3">
          <FooterCard label="SoP regime" value="NSW SOP Act 1999" sub="Notice clause 36.1 · 20-day bar" />
          <FooterCard label="Sources analysed" value="148 documents" sub="RFIs · Site instr. · Minutes" />
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas p-3">
      <div className="text-[11px] text-ink-subtle">{label}</div>
      <div className={`mt-1 text-xl font-semibold tabular-nums ${alert ? "text-amber-400" : "text-ink"}`}>
        {value}
      </div>
    </div>
  );
}

function VariationRow({
  title, band, score, value, timeBar, evidence,
}: {
  title: string; band: "high" | "medium" | "low"; score: string;
  value: string; timeBar?: string; evidence: string;
}) {
  const bandColor =
    band === "high" ? "text-success" : band === "medium" ? "text-ink-muted" : "text-ink-subtle";
  return (
    <div className="flex items-center justify-between gap-3 border-b border-hairline px-3 py-2.5 last:border-0">
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium text-ink">{title}</div>
        <div className="mt-0.5 flex items-center gap-2 text-[11px]">
          <span className={bandColor}>{band} · {score}</span>
          {timeBar && (
            <span className="inline-flex items-center gap-1 rounded-pill bg-amber-500/10 px-1.5 py-0.5 font-medium text-amber-400">
              ⚠ time-bar {timeBar}
            </span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-[13px] font-semibold tabular-nums text-ink">{value}</span>
        <span className="rounded-md border border-hairline bg-surface-2 px-1.5 py-0.5 text-[11px] text-primary-hover">
          {evidence} ↗
        </span>
      </div>
    </div>
  );
}

function FooterCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-canvas p-3">
      <div className="text-[11px] text-ink-subtle">{label}</div>
      <div className="mt-1 text-[13px] font-semibold text-ink">{value}</div>
      <div className="mt-0.5 text-[11px] text-ink-subtle">{sub}</div>
    </div>
  );
}

/* ---------------- section: how it works ---------------- */
function HowItWorks() {
  const steps = [
    {
      n: "01", title: "Ingest",
      body: "Connect your project record — RFIs, site instructions, meeting minutes and comms, by upload or CSV. VariationIQ normalises every source into one timeline.",
    },
    {
      n: "02", title: "Detect",
      body: "AI reads the agreed contract baseline against every communication and surfaces work that was instructed or performed but never claimed.",
    },
    {
      n: "03", title: "Recover",
      body: "Each variation arrives with a confidence score, an AUD estimate, a time-bar countdown, and evidence linked to its source — ready for your commercial team.",
    },
  ];
  return (
    <section className="relative border-t border-hairline/60">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <p className="va-eyebrow">How it works</p>
        <h2 className="mt-2 max-w-2xl text-[clamp(1.8rem,3.5vw,2.5rem)] font-semibold tracking-tightest">
          From project records to recoverable revenue.
        </h2>
        <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className="va-panel p-6">
              <div className="font-mono text-sm text-primary-hover">{s.n}</div>
              <h3 className="mt-3 text-lg font-semibold tracking-tight">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: features ---------------- */
function Features() {
  const caps = [
    { title: "Multi-source ingestion", body: "RFIs, site instructions, meeting minutes and project comms — parsed and normalised, not just stored." },
    { title: "AI variation detection", body: "Finds out-of-scope and unclaimed work across the entire project record, clustered with its rationale." },
    { title: "AUD value & time-bar risk", body: "Recoverable estimates in AUD, plus Security of Payment notice deadlines flagged before they lapse." },
    { title: "Evidence-linked audit trail", body: "Every finding traces back to the exact source document, with an immutable record of each review decision." },
  ];
  const trades = ["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering", "Large builders"];
  return (
    <section className="relative border-t border-hairline/60">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <p className="va-eyebrow">Capabilities</p>
        <h2 className="mt-2 max-w-2xl text-[clamp(1.8rem,3.5vw,2.5rem)] font-semibold tracking-tightest">
          A revenue-recovery engine, not another document store.
        </h2>
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {caps.map((c) => (
            <div key={c.title} className="va-panel p-6">
              <div className="grid h-8 w-8 place-items-center rounded-md bg-primary/15 text-primary-hover">◆</div>
              <h3 className="mt-4 text-base font-semibold tracking-tight">{c.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{c.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-12">
          <p className="va-eyebrow mb-3">Built for every trade</p>
          <div className="flex flex-wrap gap-2">
            {trades.map((t) => (
              <span key={t} className="rounded-md border border-hairline bg-surface-1 px-3 py-1.5 text-[13px] text-ink-muted">
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
function TrustBand() {
  const items = [
    {
      title: "Australia-wide Security of Payment awareness",
      body: "Notice periods and time-bar logic account for state and territory SoP regimes.",
    },
    {
      title: "Four supported document sources",
      body: "RFIs, site instructions, meeting minutes and project communications.",
    },
    {
      title: "Every variation linked to supporting evidence",
      body: "Each finding traces back to the source document it was detected from.",
    },
  ];
  return (
    <section className="relative border-t border-hairline/60">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <p className="va-eyebrow mb-6">Product capabilities</p>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {items.map((i) => (
            <div key={i.title} className="flex gap-3">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-[5px] bg-primary/15 text-[11px] text-primary-hover">
                ✓
              </span>
              <div>
                <div className="text-sm font-semibold text-ink">{i.title}</div>
                <div className="mt-1 text-[13px] leading-relaxed text-ink-subtle">{i.body}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: closing CTA ---------------- */
function CtaBanner() {
  return (
    <section className="relative border-t border-hairline/60">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="relative overflow-hidden rounded-xl border border-hairline-strong bg-surface-1 p-10 text-center sm:p-14">
          <div aria-hidden className="pointer-events-none absolute -top-24 left-1/2 h-64 w-[600px] -translate-x-1/2 rounded-full bg-primary/15 blur-[120px]" />
          <h2 className="relative text-[clamp(1.8rem,3.5vw,2.6rem)] font-semibold tracking-tightest">
            Stop leaving variations unclaimed.
          </h2>
          <p className="relative mx-auto mt-3 max-w-xl text-ink-muted">
            See what your projects are owed. Run a free analysis on your own project record in minutes.
          </p>
          <div className="relative mt-7 flex flex-wrap justify-center gap-3">
            <Link href="/login" className="rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-hover">
              Start Free Analysis
            </Link>
            <Link href="#demo" className="rounded-md border border-hairline bg-surface-1 px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-surface-2">
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
          <span className="text-[12px] text-ink-subtle">· AI revenue recovery for Australian construction</span>
        </div>
        <p className="text-[12px] text-ink-tertiary">
          © 2026 VariationIQ · Estimates only — not legal advice.
        </p>
      </div>
    </footer>
  );
}
