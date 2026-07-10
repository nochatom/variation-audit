import Link from "next/link";
import { FileCheck2, Files, Gavel, Inbox, Link2, ScanSearch, ShieldAlert } from "lucide-react";
import { Chip, ConfidenceBar, StatCard, TimeBarFlag, aud } from "@/components/ui";
import { LogoMark } from "@/components/ui/Logo";

/* ---------------- nav ---------------- */
export function Nav() {
  return (
    <header className="sticky top-0 z-30 h-14 border-b border-ip-line bg-ip-bg/85 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-6 sm:px-12 lg:px-16">
        <Link href="/" className="flex items-center gap-2.5" aria-label="VariationIQ home">
          <LogoMark size={28} />
          <span className="text-[15px] font-bold tracking-tight text-ip-ink">VariationIQ</span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-ip-ink-2 md:flex">
          {/* Root-relative (/#id), not bare #id — this nav renders on every
              marketing page, and a bare hash silently no-ops anywhere the
              target section doesn't exist (e.g. /pricing). */}
          <Link href="/#preview" className="transition-colors hover:text-ip-ink">Product</Link>
          <Link href="/#how" className="transition-colors hover:text-ip-ink">How it works</Link>
          <Link href="/#capabilities" className="transition-colors hover:text-ip-ink">Capabilities</Link>
          <Link href="/pricing" className="transition-colors hover:text-ip-ink">Pricing</Link>
        </nav>
        <div className="flex items-center gap-2">
          <Link href="/login" className="rounded-md px-3 py-1.5 text-sm font-medium text-ip-ink-2 transition-colors hover:text-ip-ink">
            Sign in
          </Link>
          <Link href="/login" className="btn-navy px-3.5 py-1.5 text-sm">
            Get started
          </Link>
        </div>
      </div>
    </header>
  );
}

/* ---------------- hero ---------------- */
export function Hero() {
  return (
    <section className="relative flex min-h-[calc(100vh-56px)] w-full items-center border-b border-ip-line">
      <div className="mx-auto grid w-full max-w-[1440px] grid-cols-1 items-center gap-y-14 px-6 py-16 sm:px-12 lg:grid-cols-[11fr_9fr] lg:gap-x-16 lg:px-16 lg:py-0">
        <div>
          <span className="inline-flex items-center gap-2 rounded-pill border border-ip-line bg-ip-card px-3 py-1 text-[12px] font-semibold text-ip-ink-2">
            <span className="h-1.5 w-1.5 rounded-full bg-ip-navy" />
            AI revenue recovery for Australian construction
          </span>

          <h1 className="mt-6 text-[clamp(2.5rem,4.6vw,3.75rem)] font-bold leading-[1.05] tracking-tight text-ip-ink">
            Find the variation revenue already buried in your projects.
          </h1>

          <p className="mt-5 max-w-lg text-[17px] leading-relaxed text-ip-ink-2">
            VariationIQ reads your contracts, RFIs, emails, site instructions and meeting
            minutes to surface unclaimed variations before the time-bar closes.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link href="/login" className="btn-navy px-6 py-3 text-[15px]">
              Start Free Analysis
            </Link>
            <a href="#preview" className="btn-ghost px-6 py-3 text-[15px]">
              Book a Demo
            </a>
          </div>

          <div className="mt-12">
            <p className="ip-label mb-3">Built for AU construction trades</p>
            <div className="flex flex-wrap gap-2">
              {["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering"].map((t) => (
                <span key={t} className="rounded-md border border-ip-line bg-ip-card px-2.5 py-1 text-[12px] text-ip-ink-3">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div>
          <ScreenshotPreview />
          <WorkflowChain />
        </div>
      </div>
    </section>
  );
}

/* ---------------- hero right side: product screenshot placeholder ---------------- */
function ScreenshotPreview() {
  return (
    <div id="preview" className="relative scroll-mt-20">
      <div className="ip-card-lg overflow-hidden">
        <div className="flex items-center justify-between border-b border-ip-line bg-ip-card-2 px-4 py-2.5">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-ip-line-strong" />
            <span className="h-2.5 w-2.5 rounded-full bg-ip-line-strong" />
            <span className="h-2.5 w-2.5 rounded-full bg-ip-line-strong" />
          </div>
          <div className="rounded-md border border-ip-line bg-ip-bg px-3 py-1 text-[11px] text-ip-ink-3">
            https://variationiq.com
          </div>
          <span className="w-10" />
        </div>

        <div className="p-4 sm:p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-[11px] text-ip-ink-3">Projects / Sydney Metro</div>
              <div className="text-sm font-semibold text-ip-ink">Package 4 — Electrical</div>
            </div>
            <Chip tone="recovery">Analysis complete</Chip>
          </div>

          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <StatCard label="Recoverable" value={aud(284500)} hint="AUD" accent="recovery" />
            <StatCard label="Variations" value="12" hint="detected" />
            <StatCard label="Time-bar risk" value="3" hint="within 14 days" accent="risk" />
          </div>

          <div className="mt-2.5 overflow-hidden rounded-lg border border-ip-line">
            <div className="flex items-center justify-between border-b border-ip-line bg-ip-card-2 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-ip-ink-3">
              <span>Detected variations</span>
              <span>Value · Confidence</span>
            </div>
            <PreviewRow title="Additional GPOs beyond contract scope" score={0.86} value={aud(4200)} timeBar />
            <PreviewRow title="Client-directed lobby finish upgrade" score={0.81} value={aud(18000)} timeBar />
            <PreviewRow title="Latent ground conditions — extra excavation" score={0.64} value={aud(12500)} />
          </div>

          <p className="mt-3 text-center text-[11px] text-ip-ink-3">Illustrative sample data — not live</p>
        </div>
      </div>
    </div>
  );
}

function PreviewRow({ title, score, value, timeBar }: { title: string; score: number; value: string; timeBar?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-ip-line px-3 py-2.5 last:border-0">
      <div className="min-w-0">
        <div className="truncate text-[12.5px] font-medium text-ip-ink">{title}</div>
        <div className="mt-1 flex items-center gap-2">
          <ConfidenceBar score={score} />
          <TimeBarFlag risk={!!timeBar} />
        </div>
      </div>
      <span className="shrink-0 text-[13px] font-semibold tabular-nums text-ip-ink">{value}</span>
    </div>
  );
}

/* ---------------- hero right side: workflow chain ---------------- */
const WORKFLOW: { label: string; tone: "input" | "core" | "output" }[] = [
  { label: "Contract", tone: "input" },
  { label: "Email", tone: "input" },
  { label: "RFI", tone: "input" },
  { label: "Site Instruction", tone: "input" },
  { label: "Meeting Minutes", tone: "input" },
  { label: "AI Detection", tone: "core" },
  { label: "Variation", tone: "output" },
  { label: "Recoverable Value", tone: "output" },
  { label: "Evidence-linked Report", tone: "output" },
];

const CHAIN_TONE: Record<string, string> = {
  input: "border border-ip-line bg-ip-card text-ip-ink-2",
  core: "border border-ip-navy-fill bg-ip-navy-fill text-white",
  output: "border border-ip-recovery/25 bg-ip-recovery/10 text-ip-recovery",
};

function WorkflowChain() {
  return (
    <div className="mt-5">
      <p className="ip-label mb-3">How it gets there</p>
      <div className="flex flex-wrap items-center gap-y-2">
        {WORKFLOW.map((step, i) => (
          <div key={step.label} className="flex items-center">
            {i > 0 && (
              <svg
                viewBox="0 0 24 24"
                className="mx-1 h-3.5 w-3.5 shrink-0 text-ip-line-strong"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M9 6l6 6-6 6" />
              </svg>
            )}
            <span className={`inline-flex items-center whitespace-nowrap rounded-pill px-3 py-1.5 text-[12px] font-semibold ${CHAIN_TONE[step.tone]}`}>
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- section heading helper ---------------- */
function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="max-w-2xl">
      <p className="ip-label">{eyebrow}</p>
      <h2 className="mt-3 text-[clamp(1.9rem,3.6vw,2.6rem)] font-bold tracking-tight text-ip-ink">{title}</h2>
    </div>
  );
}

/* ---------------- section: how it works ---------------- */
export function HowItWorks() {
  const steps = [
    { n: "01", title: "Ingest", body: "Connect your project record — RFIs, site instructions, meeting minutes and comms, by upload or CSV. VariationIQ normalises every source into one timeline." },
    { n: "02", title: "Detect", body: "AI reads the agreed contract baseline against every communication and surfaces work that was instructed or performed but never claimed." },
    { n: "03", title: "Recover", body: "Each variation arrives with a confidence score, an AUD estimate, a time-bar countdown, and evidence linked to its source — ready for your commercial team." },
  ];
  return (
    <section id="how" className="relative border-b border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-24 sm:px-12 lg:px-16">
        <SectionHeading eyebrow="How it works" title="From project records to recoverable revenue." />
        <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-3">
          {steps.map((s) => (
            <div key={s.n} className="ip-card p-6">
              <div className="flex items-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-lg border border-ip-line bg-ip-card-2 font-mono text-sm text-ip-navy">
                  {s.n}
                </span>
                <h3 className="text-lg font-semibold tracking-tight text-ip-ink">{s.title}</h3>
              </div>
              <p className="mt-4 text-sm leading-relaxed text-ip-ink-2">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: capabilities (feature cards + trades) ---------------- */
export function Features() {
  const caps = [
    { title: "Multi-source ingestion", body: "RFIs, site instructions, meeting minutes and project comms — parsed and normalised, not just stored.", icon: Inbox },
    { title: "AI variation detection", body: "Finds out-of-scope and unclaimed work across the entire project record, clustered with its rationale.", icon: ScanSearch },
    { title: "AUD value & time-bar risk", body: "Recoverable estimates in AUD, plus Security of Payment notice deadlines flagged before they lapse.", icon: ShieldAlert },
    { title: "Evidence-linked audit trail", body: "Every finding traces back to the exact source document, with an immutable record of each review decision.", icon: Link2 },
  ];
  const trades = ["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering", "Large builders"];
  return (
    <section id="capabilities" className="relative border-b border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-24 sm:px-12 lg:px-16">
        <SectionHeading eyebrow="Capabilities" title="A revenue-recovery engine, not another document store." />
        <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {caps.map((c) => (
            <div
              key={c.title}
              className="group rounded-xl border border-ip-line bg-ip-card p-7 shadow-ip-card transition-all duration-200 hover:-translate-y-0.5 hover:border-ip-line-strong hover:shadow-ip-pop"
            >
              <div className="grid h-11 w-11 place-items-center rounded-lg border border-ip-navy/15 bg-ip-navy/8 text-ip-navy transition-colors duration-200 group-hover:bg-ip-navy/12">
                <c.icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
              </div>
              <h3 className="mt-5 text-base font-semibold leading-snug tracking-tight text-ip-ink">{c.title}</h3>
              <p className="mt-2.5 text-sm leading-relaxed text-ip-ink-2">{c.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-14">
          <p className="ip-label mb-4">Built for every trade</p>
          <div className="flex flex-wrap gap-2.5">
            {trades.map((t) => (
              <span key={t} className="rounded-lg border border-ip-line bg-ip-card px-3.5 py-2 text-[13px] text-ip-ink-2 transition-colors hover:border-ip-line-strong hover:text-ip-ink">
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
export function ProductCapabilities() {
  const items = [
    { title: "Australia-wide Security of Payment awareness", body: "Notice periods and time-bar logic account for state and territory SoP regimes.", icon: Gavel },
    { title: "Four supported document sources", body: "RFIs, site instructions, meeting minutes and project communications.", icon: Files },
    { title: "Every variation linked to supporting evidence", body: "Each finding traces back to the source document it was detected from.", icon: FileCheck2 },
  ];
  return (
    <section className="relative border-b border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-20 sm:px-12 lg:px-16">
        <p className="ip-label mb-7">Product capabilities</p>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
          {items.map((i) => (
            <div
              key={i.title}
              className="group rounded-xl border border-ip-line bg-ip-card p-6 shadow-ip-card transition-all duration-200 hover:-translate-y-0.5 hover:border-ip-line-strong hover:shadow-ip-pop"
            >
              <div className="flex items-center gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-ip-navy/15 bg-ip-navy/8 text-ip-navy transition-colors duration-200 group-hover:bg-ip-navy/12">
                  <i.icon className="h-[18px] w-[18px]" strokeWidth={1.75} aria-hidden />
                </span>
                <div className="text-sm font-semibold leading-snug text-ip-ink">{i.title}</div>
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-ip-ink-3">{i.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- section: closing CTA ---------------- */
export function CtaBanner() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-[1440px] px-6 py-24 sm:px-12 lg:px-16">
        <div className="rounded-2xl border border-ip-line bg-ip-card-2 p-12 text-center sm:p-16">
          <h2 className="text-[clamp(1.9rem,3.6vw,2.8rem)] font-bold tracking-tight text-ip-ink">
            Stop leaving variations unclaimed.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-ip-ink-2">
            See what your projects are owed. Run a free analysis on your own project record in minutes.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/login" className="btn-navy px-6 py-3 text-[15px]">
              Start Free Analysis
            </Link>
            <a href="#preview" className="btn-ghost px-6 py-3 text-[15px]">
              Book a Demo
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- footer ---------------- */
const FOOTER_COLUMNS: { label: string; links: { title: string; href: string }[] }[] = [
  {
    label: "Product",
    links: [
      { title: "Product preview", href: "/#preview" },
      { title: "How it works", href: "/#how" },
      { title: "Capabilities", href: "/#capabilities" },
      { title: "Pricing", href: "/pricing" },
    ],
  },
  {
    label: "Company",
    links: [{ title: "About", href: "/about" }],
  },
  {
    label: "Legal",
    links: [
      { title: "Privacy Policy", href: "/privacy" },
      { title: "Terms of Service", href: "/terms" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="relative border-t border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-12 sm:px-12 lg:px-16">
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="col-span-2 sm:col-span-1">
            <Link href="/" className="flex items-center gap-2.5" aria-label="VariationIQ home">
              <LogoMark size={28} />
              <span className="text-[15px] font-bold tracking-tight text-ip-ink">VariationIQ</span>
            </Link>
            <p className="mt-3 max-w-xs text-[13px] leading-relaxed text-ip-ink-3">
              AI revenue recovery for Australian construction — surfacing unclaimed variations from your project
              records before the time bar closes.
            </p>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <div key={col.label}>
              <h3 className="text-[12px] font-semibold uppercase tracking-wide text-ip-ink-3">{col.label}</h3>
              <ul className="mt-3 space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.title}>
                    <Link href={link.href} className="text-[13px] text-ip-ink-2 transition-colors hover:text-ip-ink">
                      {link.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <div>
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-ip-ink-3">Contact</h3>
            <ul className="mt-3 space-y-2.5">
              <li>
                <a href="mailto:hello@variationiq.com" className="text-[13px] text-ip-ink-2 transition-colors hover:text-ip-ink">
                  hello@variationiq.com
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 flex flex-col gap-2 border-t border-ip-line pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[12px] text-ip-ink-3">© {new Date().getFullYear()} VariationIQ · Estimates only — not legal advice.</p>
          <p className="text-[12px] text-ip-ink-3">Sydney, Australia</p>
        </div>
      </div>
    </footer>
  );
}
