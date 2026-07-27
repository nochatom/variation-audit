import Link from "next/link";
import { Gavel, Inbox, Link2, ScanSearch } from "lucide-react";
import { Chip, ConfidenceBar, StatCard, TimeBarFlag, aud } from "@/components/ui";
import { MobileMenu } from "@/components/home/mobile-menu";
import { LogoMark } from "@/components/ui/Logo";
import { Wordmark } from "@/components/ui/Wordmark";

/* ---------------- nav ----------------
   Root-relative (/#id), not bare #id — this nav renders on every marketing
   page, and a bare hash silently no-ops anywhere the target section doesn't
   exist (e.g. /pricing).

   "Product" used to point at /#preview, the sample panel inside the hero —
   i.e. it scrolled you to the top of the page you were already on. It now
   names what it actually reaches. */
const NAV_LINKS = [
  { href: "/#how", label: "How it works" },
  { href: "/#capabilities", label: "Capabilities" },
  { href: "/pricing", label: "Pricing" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-30 h-14 border-b border-ip-line bg-ip-bg/85 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-6 sm:px-12 lg:px-16">
        <Link
          href="/"
          className="-ml-2 flex min-h-[44px] items-center gap-2.5 rounded-md px-2"
          aria-label="VariationIQ home"
        >
          <LogoMark size={28} />
          <Wordmark height={17} className="text-ip-ink" />
        </Link>

        {/* Links sit at 44px tall (they were 20px) — the hit area grows, the
            type does not. */}
        <nav className="hidden items-center gap-2 text-sm text-ip-ink-2 md:flex">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="flex min-h-[44px] items-center rounded-md px-3 transition-colors hover:text-ip-ink"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1 sm:gap-2">
          {/* Sign in stays a quiet text link and Get started keeps the fill:
              one action leads. They also now resolve to different tabs —
              previously both hit /login and both opened the login form. */}
          <Link
            href="/login"
            className="hidden min-h-[44px] items-center rounded-md px-3 text-sm font-medium text-ip-ink-2 transition-colors hover:text-ip-ink sm:flex"
          >
            Sign in
          </Link>
          {/* Stays visible at every width. Hiding it behind the mobile menu
              traded the header's one job for a hamburger — wayfinding belongs
              in the menu, the primary action does not. */}
          <Link href="/login?mode=signup" className="btn-navy min-h-[44px] px-4 text-sm">
            Get started
          </Link>
          <MobileMenu links={NAV_LINKS} />
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
          <span
            className="animate-fade-up inline-flex items-center gap-2 rounded-pill border border-ip-line bg-ip-card px-3 py-1 text-[12px] font-semibold text-ip-ink-2"
            style={{ animationDelay: "0ms" }}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-ip-navy" />
            AI revenue recovery for Australian construction
          </span>

          <h1
            className="animate-fade-up mt-6 text-[clamp(2.5rem,4.6vw,3.75rem)] font-bold leading-[1.05] tracking-tight text-ip-ink"
            style={{ animationDelay: "60ms" }}
          >
            Find the variation revenue already buried in your projects.
          </h1>

          <p
            className="animate-fade-up mt-5 max-w-lg text-[17px] leading-relaxed text-ip-ink-2"
            style={{ animationDelay: "120ms" }}
          >
            VariationIQ reads your contracts, RFIs, emails, site instructions and meeting
            minutes to surface unclaimed variations before the time-bar closes.
          </p>

          {/* Secondary CTA says what it actually does. It is an in-page anchor
              to the sample panel (#preview) — labelling it "Book a Demo" made a
              promise the button never kept, and on desktop its target is already
              on screen. It earns its place on mobile, where the proof sits below
              the fold. */}
          <div className="animate-fade-up mt-10 flex flex-wrap items-center gap-3" style={{ animationDelay: "180ms" }}>
            <Link href="/login" className="btn-navy px-6 py-3 text-[15px]">
              Start Free Analysis
            </Link>
            <a href="#preview" className="btn-ghost px-6 py-3 text-[15px] lg:hidden">
              See a sample analysis
            </a>
          </div>

          {/* DELETED: the "Built for AU construction trades" chips. The eyebrow
              and headline already establish the market, Features() renders the
              same list (plus one more) further down, and on mobile the block
              wedged itself between the CTA and the product proof. */}
        </div>

        {/* DELETED: WorkflowChain. HowItWorks() below is the same pipeline
            (Ingest → Detect → Recover) told properly — the hero was explaining
            mechanics before the visitor had accepted the premise. */}
        <div className="animate-fade-up" style={{ animationDelay: "150ms" }}>
          <ScreenshotPreview />
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
          {/* The "Analysis complete" chip was a fifth colour signal saying what
              the panel already shows. Cut, so green means one thing here:
              money recovered. */}
          <div className="mb-4">
            <div className="text-[11px] text-ip-ink-3">Projects / Sydney Metro</div>
            <div className="text-sm font-semibold text-ip-ink">Package 4 — Electrical</div>
          </div>

          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <StatCard size="sm" label="Recoverable" value={aud(284500)} hint="AUD" accent="recovery" />
            <StatCard size="sm" label="Variations" value="12" hint="detected" />
            <StatCard size="sm" label="Time-bar risk" value="3" hint="within 14 days" accent="risk" />
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
        {/* The flag only appears when there IS risk. A green "on track" on every
            other row spent a colour to say "nothing to see here", while the
            Time-bar risk stat card above already carries the count. */}
        <div className="mt-1 flex items-center gap-2">
          <ConfidenceBar score={score} />
          {timeBar && <TimeBarFlag risk />}
        </div>
      </div>
      <span className="shrink-0 text-[13px] font-semibold tabular-nums text-ip-ink">{value}</span>
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

/* ---------------- section: how it works ----------------
   Deliberately NOT three equal cards. Ingest is table stakes (every tool
   accepts uploads) and Recover is output formatting; detection against the
   contract baseline is the only step a competitor can't trivially copy. So
   Detect gets the width, the word budget and — most importantly — the only
   thing on this section that isn't a claim: a worked example. The supporting
   steps shrink to a single line each. */
export function HowItWorks() {
  return (
    <section id="how" className="relative border-b border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-24 sm:px-12 lg:px-16">
        <SectionHeading eyebrow="How it works" title="From project records to recoverable revenue." />

        {/* Source order is 01 → 02 → 03 so the stacked mobile layout reads in
            sequence; the two-column desktop arrangement is produced by explicit
            placement, not by source order. Nesting the asides in their own
            column made mobile read 01 → 03 → 02. */}
        <div className="mt-12 grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.85fr] lg:items-start">
          <StepAside
            n="01"
            title="Ingest"
            body="RFIs, site instructions, meeting minutes and comms — by upload or CSV, normalised into one timeline."
            className="lg:col-start-1 lg:row-start-1"
          />

          {/* the protagonist */}
          <div className="ip-card-lg p-6 sm:p-8 lg:col-start-2 lg:row-start-1 lg:row-span-2">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm text-ip-ink-3">02</span>
              <h3 className="text-[22px] font-bold tracking-tight text-ip-ink">Detect</h3>
            </div>
            <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-ip-ink-2">
              VariationIQ reads the agreed contract baseline against every communication on the job,
              and flags work that was instructed or performed but never claimed.
            </p>
            <DetectionExample />
          </div>

          <StepAside
            n="03"
            title="Recover"
            body="Every variation lands with its dollar estimate, time-bar countdown and evidence, ready to claim."
            className="lg:col-start-1 lg:row-start-2"
          />
        </div>
      </div>
    </section>
  );
}

/** Supporting step: no card fill, no bordered numeral box. The number is just a
 *  number — the reading order already communicates sequence, so the box that
 *  used to hold it was decoration. */
function StepAside({ n, title, body, className = "" }: { n: string; title: string; body: string; className?: string }) {
  return (
    // Sizes to its content (the grid is items-start): stretching these to match
    // Detect's height left a band of dead space under each, which reads as a
    // layout bug rather than restraint.
    <div className={`rounded-lg border border-ip-line p-5 ${className}`}>
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm text-ip-ink-3">{n}</span>
        <h3 className="text-base font-semibold tracking-tight text-ip-ink">{title}</h3>
      </div>
      <p className="mt-2 text-[13.5px] leading-relaxed text-ip-ink-2">{body}</p>
    </div>
  );
}

/** The worked example — the one thing in this section that isn't a claim.
 *  Shows the actual transformation: an ordinary line in a site instruction on
 *  the left, the variation it produces on the right. Built from the same
 *  primitives the product renders (ConfidenceBar, Chip, aud) rather than
 *  drawn, and labelled as illustrative — the hero makes the same promise and
 *  breaking it here would cost more than the section is worth. */
function DetectionExample() {
  return (
    <div className="mt-6">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_1fr] md:items-center">
        {/* evidence in */}
        <div className="rounded-lg border border-ip-line bg-ip-card-2 p-4">
          <p className="ip-label mb-2">Site instruction · 14 Mar</p>
          <p className="text-[13px] leading-relaxed text-ip-ink-2">
            &ldquo;Confirming site walk today — client wants{" "}
            <mark className="rounded bg-ip-orange/20 px-0.5 text-ip-ink">four extra GPOs in the plant room</mark>{" "}
            before ceilings close. Proceed and we&rsquo;ll sort the paperwork later.&rdquo;
          </p>
        </div>

        {/* ink-3, not line-strong: this arrow carries the meaning of the whole
            example (evidence becomes variation). At #c5c6cd it sat near 1.9:1
            and failed the 3:1 floor for meaningful non-text graphics. */}
        <svg
          viewBox="0 0 24 24"
          className="mx-auto h-5 w-5 shrink-0 rotate-90 text-ip-ink-3 md:rotate-0"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>

        {/* variation out */}
        <div className="rounded-lg border border-ip-line bg-ip-card p-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[13px] font-semibold text-ip-ink">Additional GPOs beyond contract scope</p>
            <span className="shrink-0 text-[13px] font-semibold tabular-nums text-ip-recovery">{aud(4200)}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <ConfidenceBar score={0.86} />
            <Chip tone="orange">Time bar in 6 days</Chip>
          </div>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-ip-ink-3">
        Illustrative example — not live data. &ldquo;Sort the paperwork later&rdquo; is where the money goes missing.
      </p>
    </div>
  );
}

/* ---------------- section: capabilities ----------------
   Four capabilities, not seven cards across two sections. Security of Payment
   is the protagonist: ingestion, detection and audit trails are things a
   competent document-AI vendor can build, but jurisdiction-specific time-bar
   logic is the part that requires knowing Australian construction law, and it
   is the reason a missed variation becomes unrecoverable rather than merely
   late. It gets the width; the rest support it. */
export function Features() {
  const supporting = [
    { title: "Multi-source ingestion", body: "RFIs, site instructions, meeting minutes and project comms — parsed and normalised, not just stored.", icon: Inbox },
    { title: "AI variation detection", body: "Finds out-of-scope and unclaimed work across the entire project record, clustered with its rationale.", icon: ScanSearch },
    { title: "Evidence-linked audit trail", body: "Every finding traces back to its source document, with an immutable record of each review decision.", icon: Link2 },
  ];
  const trades = ["General Contractors", "Electrical", "Plumbing", "HVAC", "Civil Engineering", "Large builders"];
  return (
    <section id="capabilities" className="relative border-b border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-24 sm:px-12 lg:px-16">
        <SectionHeading eyebrow="Capabilities" title="A revenue-recovery engine, not another document store." />

        {/* Protagonist. Two columns rather than one long line: a single text
            block stopped around 60% of the card, leaving the border drawing a
            box around empty space — which reads as unfinished rather than as
            restraint. Heading left, argument right, both using the width. */}
        <div className="ip-card-lg mt-12 p-7 sm:p-9">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-14">
            <div className="flex gap-5">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg border border-ip-navy/15 bg-ip-navy/8 text-ip-navy">
                <Gavel className="h-6 w-6" strokeWidth={1.6} aria-hidden />
              </div>
              <h3 className="text-[26px] font-bold leading-[1.15] tracking-tight text-ip-ink">
                Time-bar risk,
                <br className="hidden sm:block" /> by jurisdiction
              </h3>
            </div>

            <div>
              {/* Absorbs the one sentence worth keeping from the deleted
                  "Product capabilities" section — the state/territory nuance. */}
              <p className="text-[15px] leading-relaxed text-ip-ink-2">
                Recoverable estimates in AUD, with Security of Payment notice deadlines flagged before
                they lapse. Notice periods and time-bar logic account for state and territory SoP regimes.
              </p>
              <p className="mt-4 text-[15px] font-semibold leading-relaxed text-ip-ink">
                Entitlement doesn&rsquo;t weaken when a deadline passes. It ends.
              </p>
            </div>
          </div>
        </div>

        {/* supporting — no hover lift: these aren't clickable, and a card that
            rises under the cursor promises an interaction that never arrives. */}
        <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-3">
          {supporting.map((c) => (
            <div key={c.title} className="rounded-xl border border-ip-line bg-ip-card p-6">
              <div className="grid h-10 w-10 place-items-center rounded-lg border border-ip-navy/15 bg-ip-navy/8 text-ip-navy">
                <c.icon className="h-[18px] w-[18px]" strokeWidth={1.75} aria-hidden />
              </div>
              <h3 className="mt-4 text-[15px] font-semibold leading-snug tracking-tight text-ip-ink">{c.title}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-ip-ink-2">{c.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-14">
          <p className="ip-label mb-4">Built for every trade</p>
          <div className="flex flex-wrap gap-2.5">
            {trades.map((t) => (
              <span key={t} className="rounded-lg border border-ip-line bg-ip-card px-3.5 py-2 text-[13px] text-ip-ink-2">
                {t}
              </span>
            ))}
          </div>
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

/* ---------------- footer ----------------
   Two columns, not four. "Company" and "Legal" held one and two links; a 12px
   uppercase header plus its spacing is more chrome than a single line of
   content deserves, so they're merged into one column that earns its label.
   Contact moved into the brand block — an email address is identity, not
   navigation, and as a standalone column it was the fifth child in a
   four-track grid, wrapping to its own row with the full width of the footer
   empty beside it.

   "Product preview" (/#preview) is gone: it scrolled to the sample panel near
   the top of the page you were already on. The header nav dropped that same
   link earlier, and a footer that contradicts the header is worse than one
   link short. */
const FOOTER_COLUMNS: { label: string; links: { title: string; href: string }[] }[] = [
  {
    label: "Product",
    links: [
      { title: "How it works", href: "/#how" },
      { title: "Capabilities", href: "/#capabilities" },
      { title: "Pricing", href: "/pricing" },
    ],
  },
  {
    label: "Company",
    links: [
      { title: "About", href: "/about" },
      { title: "Privacy Policy", href: "/privacy" },
      { title: "Terms of Service", href: "/terms" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="relative border-t border-ip-line">
      <div className="mx-auto max-w-[1440px] px-6 py-12 sm:px-12 lg:px-16">
        {/* Track count now matches the child count — brand + two columns.
            The link columns stay side by side on mobile: stacking them made the
            footer taller than the four-column version it replaced (769px vs
            617px), which is the opposite of the point. */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-[1.6fr_1fr_1fr] sm:gap-8">
          <div className="col-span-2 sm:col-span-1">
            <Link
              href="/"
              className="-ml-2 flex min-h-[44px] w-fit items-center gap-2.5 rounded-md px-2"
              aria-label="VariationIQ home"
            >
              <LogoMark size={28} />
              <Wordmark height={17} className="text-ip-ink" />
            </Link>
            <p className="mt-3 max-w-xs text-[13px] leading-relaxed text-ip-ink-3">
              AI revenue recovery for Australian construction — surfacing unclaimed variations from your project
              records before the time bar closes.
            </p>
            <a
              href="mailto:hello@variationiq.com"
              className="mt-3 inline-flex min-h-[44px] items-center text-[13px] text-ip-ink-2 transition-colors hover:text-ip-ink"
            >
              hello@variationiq.com
            </a>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <div key={col.label}>
              <h3 className="text-[12px] font-semibold uppercase tracking-wide text-ip-ink-3">{col.label}</h3>
              {/* Rows are 44px tall with the type unchanged: the hit area grows,
                  the visual density doesn't. */}
              <ul className="mt-1">
                {col.links.map((link) => (
                  <li key={link.title}>
                    <Link
                      href={link.href}
                      className="flex min-h-[44px] items-center text-[13px] text-ip-ink-2 transition-colors hover:text-ip-ink"
                    >
                      {link.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col gap-2 border-t border-ip-line pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[12px] text-ip-ink-3">© {new Date().getFullYear()} VariationIQ · Estimates only — not legal advice.</p>
          <p className="text-[12px] text-ip-ink-3">Sydney, Australia</p>
        </div>
      </div>
    </footer>
  );
}
