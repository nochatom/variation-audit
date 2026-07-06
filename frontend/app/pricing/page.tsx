"use client";

import Link from "next/link";
import { useState } from "react";
import { Nav, SiteFooter } from "@/components/home/sections";
import { Chip } from "@/components/ui";

/* ---------------- pricing data ---------------- */
type Plan = {
  tier: "free" | "pro" | "enterprise";
  label: string;
  tagline: string;
  monthly: number | null;
  annual: number | null;
  cta: string;
  ctaHref: string;
  highlighted?: boolean;
  features: string[];
};

const PLANS: Plan[] = [
  {
    tier: "free",
    label: "Free",
    tagline: "See what a single project is owed.",
    monthly: 0,
    annual: 0,
    cta: "Start Free",
    ctaHref: "/login",
    features: [
      "1 project",
      "20 documents / month",
      "5 AI analyses / month",
      "3 seats",
      "500 MB storage",
    ],
  },
  {
    tier: "pro",
    label: "Pro",
    tagline: "For teams recovering variations every month.",
    monthly: 149,
    annual: 1490,
    cta: "Upgrade to Pro",
    ctaHref: "/login",
    highlighted: true,
    features: [
      "25 projects",
      "500 documents / month",
      "100 AI analyses / month",
      "15 included seats",
      "5 GB storage",
      "PDF reports",
      "Audit log",
    ],
  },
  {
    tier: "enterprise",
    label: "Enterprise",
    tagline: "For builders and head contractors running variation recovery at scale.",
    monthly: null,
    annual: null,
    cta: "Contact Sales",
    ctaHref: "mailto:hello@variationiq.com",
    features: [
      "Unlimited projects",
      "Unlimited documents",
      "Unlimited AI analyses",
      "Unlimited seats",
      "Unlimited storage",
      "Priority support",
      "Future: SSO",
      "Future: Advanced analytics",
    ],
  },
];

const COMPARISON_ROWS: { label: string; free: string; pro: string; enterprise: string }[] = [
  { label: "Projects", free: "1", pro: "25", enterprise: "Unlimited" },
  { label: "Documents / month", free: "20", pro: "500", enterprise: "Unlimited" },
  { label: "AI analyses / month", free: "5", pro: "100", enterprise: "Unlimited" },
  { label: "Seats", free: "3", pro: "15 included", enterprise: "Unlimited" },
  { label: "Storage", free: "500 MB", pro: "5 GB", enterprise: "Unlimited" },
  { label: "PDF reports", free: "—", pro: "✓", enterprise: "✓" },
  { label: "Audit log", free: "—", pro: "✓", enterprise: "✓" },
  { label: "Priority support", free: "—", pro: "—", enterprise: "✓" },
  { label: "SSO", free: "—", pro: "—", enterprise: "Future" },
  { label: "Advanced analytics", free: "—", pro: "—", enterprise: "Future" },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "How does the ROI actually work?",
    a: "A single missed variation on a commercial project is commonly worth thousands to tens of thousands of dollars. Pro costs AUD 149/month — recovering just one variation, on one project, typically covers a year or more of the subscription. VariationIQ doesn't create revenue, it surfaces revenue you already earned but haven't claimed.",
  },
  {
    q: "What counts as an AI analysis?",
    a: "One analysis run is one full pass over a project's contract, RFIs, site instructions, meeting minutes, and comms to detect and value variations. You can re-run analysis as your project record grows.",
  },
  {
    q: "What happens if I go over my plan's limits?",
    a: "You'll see a clear message when you hit a document, analysis, or project limit, with an upgrade path. Seats work differently on Pro and Enterprise — see the next question.",
  },
  {
    q: "Can I add more than 15 seats on Pro?",
    a: "Yes. Pro includes 15 seats; additional seats beyond that are billed as seat overage on your existing subscription, so your team isn't blocked from growing.",
  },
  {
    q: "Can I switch between monthly and annual billing?",
    a: "Yes — annual billing is roughly 2 months free compared to paying monthly. Use \"Manage billing\" in Settings to change your billing interval, or contact us if you need help switching.",
  },
  {
    q: "Do you offer a free trial of Pro?",
    a: "The Free plan itself has no time limit — it's scoped to 1 project so you can fully test variation detection on a real project before upgrading, rather than a countdown trial.",
  },
  {
    q: "What does Enterprise pricing look like?",
    a: "Enterprise is custom-priced around your number of projects, seats, and support needs. Contact sales and we'll put together a quote.",
  },
];

/* ---------------- page ---------------- */
export default function PricingPage() {
  const [interval, setInterval] = useState<"monthly" | "annual">("monthly");
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  return (
    <div className="relative min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Nav />
      <main>
        {/* header */}
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[1000px] px-6 py-20 text-center sm:px-12">
            <p className="ip-label text-ip-ink-3">Pricing</p>
            <h1 className="mt-3 text-[clamp(2rem,4.2vw,3rem)] font-bold leading-[1.1] tracking-tight text-ip-ink">
              Recover revenue you already earned.
            </h1>
            <p className="mx-auto mt-4 max-w-xl text-[16px] leading-relaxed text-ip-ink-2">
              VariationIQ finds the variations buried in your project record. Most plans pay for
              themselves the first time we surface one you would have missed.
            </p>

            <div className="mt-10 inline-flex items-center gap-2 rounded-pill border border-ip-line bg-ip-card p-1 text-[13px] font-semibold">
              <button
                className={`rounded-pill px-4 py-1.5 transition-colors ${interval === "monthly" ? "bg-ip-navy text-white" : "text-ip-ink-2"}`}
                onClick={() => setInterval("monthly")}
              >
                Monthly
              </button>
              <button
                className={`rounded-pill px-4 py-1.5 transition-colors ${interval === "annual" ? "bg-ip-navy text-white" : "text-ip-ink-2"}`}
                onClick={() => setInterval("annual")}
              >
                Annual <span className="text-ip-recovery">· 2 months free</span>
              </button>
            </div>
          </div>
        </section>

        {/* plan cards */}
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[1200px] px-6 py-16 sm:px-12">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              {PLANS.map((p) => (
                <PlanCard key={p.tier} plan={p} interval={interval} />
              ))}
            </div>
          </div>
        </section>

        {/* ROI section */}
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[1000px] px-6 py-20 sm:px-12">
            <div className="ip-card-lg p-8 sm:p-12">
              <p className="ip-label mb-4">Why this pays for itself</p>
              <h2 className="text-[clamp(1.6rem,3vw,2.1rem)] font-bold tracking-tight text-ip-ink">
                One recovered variation usually covers the subscription for a year.
              </h2>
              <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-3">
                <RoiStat label="Pro plan" value="AUD 149/mo" hint="AUD 1,490/yr" />
                <RoiStat label="Typical missed variation" value="AUD 3,000–20,000+" hint="per finding, before recovery" />
                <RoiStat label="Break-even" value="1 finding" hint="often in month one" />
              </div>
              <p className="mt-8 text-[14px] leading-relaxed text-ip-ink-2">
                Variations get missed because the evidence for them is scattered across contracts,
                RFIs, emails, site instructions and meeting minutes — not because the entitlement
                isn&apos;t real. VariationIQ reads that record so your commercial team can claim what
                was already earned, before a time-bar notice period closes the window.
              </p>
            </div>
          </div>
        </section>

        {/* comparison table */}
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[1200px] px-6 py-20 sm:px-12">
            <div className="max-w-2xl">
              <p className="ip-label">Compare plans</p>
              <h2 className="mt-3 text-[clamp(1.9rem,3.6vw,2.6rem)] font-bold tracking-tight text-ip-ink">
                Every plan, side by side.
              </h2>
            </div>
            <div className="mt-10 overflow-x-auto rounded-lg border border-ip-line">
              <table className="w-full min-w-[560px] border-collapse text-left text-[13px]">
                <thead>
                  <tr className="border-b border-ip-line bg-ip-card-2">
                    <th className="px-4 py-3 font-semibold text-ip-ink-3">Feature</th>
                    <th className="px-4 py-3 font-semibold text-ip-ink">Free</th>
                    <th className="px-4 py-3 font-semibold text-ip-navy">Pro</th>
                    <th className="px-4 py-3 font-semibold text-ip-ink">Enterprise</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON_ROWS.map((row, i) => (
                    <tr key={row.label} className={i % 2 === 1 ? "bg-ip-card-2/40" : ""}>
                      <td className="border-t border-ip-line px-4 py-3 font-medium text-ip-ink-2">{row.label}</td>
                      <td className="border-t border-ip-line px-4 py-3 text-ip-ink-2">{row.free}</td>
                      <td className="border-t border-ip-line px-4 py-3 font-semibold text-ip-ink">{row.pro}</td>
                      <td className="border-t border-ip-line px-4 py-3 text-ip-ink-2">{row.enterprise}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[820px] px-6 py-20 sm:px-12">
            <div className="max-w-2xl">
              <p className="ip-label">FAQ</p>
              <h2 className="mt-3 text-[clamp(1.9rem,3.6vw,2.6rem)] font-bold tracking-tight text-ip-ink">
                Questions, answered.
              </h2>
            </div>
            <div className="mt-10 divide-y divide-ip-line border-y border-ip-line">
              {FAQ.map((item, i) => {
                const isOpen = openFaq === i;
                return (
                  <div key={item.q}>
                    <button
                      className="flex w-full items-center justify-between gap-4 py-5 text-left"
                      onClick={() => setOpenFaq(isOpen ? null : i)}
                      aria-expanded={isOpen}
                    >
                      <span className="text-[15px] font-semibold text-ip-ink">{item.q}</span>
                      <span className={`shrink-0 text-ip-ink-3 transition-transform ${isOpen ? "rotate-45" : ""}`}>+</span>
                    </button>
                    {isOpen && (
                      <p className="pb-5 text-[14px] leading-relaxed text-ip-ink-2">{item.a}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* closing CTA */}
        <section>
          <div className="mx-auto max-w-[1440px] px-6 py-24 sm:px-12 lg:px-16">
            <div className="rounded-2xl border border-ip-line bg-ip-card-2 p-12 text-center sm:p-16">
              <h2 className="text-[clamp(1.9rem,3.6vw,2.8rem)] font-bold tracking-tight text-ip-ink">
                Stop leaving variations unclaimed.
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-ip-ink-2">
                Start free on one project — see what it's already owed before you pay for anything.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                <Link href="/login" className="btn-navy px-6 py-3 text-[15px]">
                  Start Free
                </Link>
                <a href="mailto:hello@variationiq.com" className="btn-ghost px-6 py-3 text-[15px]">
                  Talk to Sales
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

/* ---------------- plan card ---------------- */
function PlanCard({ plan, interval }: { plan: Plan; interval: "monthly" | "annual" }) {
  const price = interval === "monthly" ? plan.monthly : plan.annual;
  return (
    <div
      className={`relative flex flex-col rounded-2xl border p-7 ${
        plan.highlighted ? "border-ip-navy bg-ip-card shadow-ip-pop" : "border-ip-line bg-ip-card"
      }`}
    >
      {plan.highlighted && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2">
          <Chip tone="navy">Most Popular</Chip>
        </span>
      )}
      <h3 className="text-lg font-bold tracking-tight text-ip-ink">{plan.label}</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ip-ink-3">{plan.tagline}</p>

      <div className="mt-6">
        {plan.tier === "enterprise" ? (
          <span className="text-2xl font-bold text-ip-ink">Contact Sales</span>
        ) : price === 0 ? (
          <span className="text-2xl font-bold text-ip-ink">Free</span>
        ) : (
          <>
            <span className="text-3xl font-bold tabular-nums text-ip-ink">AUD {price!.toLocaleString()}</span>
            <span className="ml-1 text-[13px] text-ip-ink-3">/ {interval === "monthly" ? "month" : "year"}</span>
          </>
        )}
        {plan.tier === "pro" && interval === "annual" && (
          <p className="mt-1 text-[12px] text-ip-recovery">≈ AUD 124/mo — 2 months free vs. monthly</p>
        )}
      </div>

      <ul className="mt-7 space-y-2.5 text-[13.5px] text-ip-ink-2">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2">
            <span className="mt-0.5 grid h-4.5 w-4.5 shrink-0 place-items-center rounded-full bg-ip-navy/10 text-[10px] text-ip-navy">✓</span>
            {f}
          </li>
        ))}
      </ul>

      <a
        href={plan.ctaHref}
        className={`mt-8 block rounded-md px-4 py-2.5 text-center text-sm font-semibold transition-colors ${
          plan.highlighted ? "btn-navy" : plan.tier === "enterprise" ? "btn-ghost" : "btn-ghost"
        }`}
      >
        {plan.cta}
      </a>
    </div>
  );
}

function RoiStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-ip-line bg-ip-card p-5">
      <div className="ip-label">{label}</div>
      <div className="mt-2 text-xl font-bold tabular-nums text-ip-ink">{value}</div>
      <div className="mt-1 text-[12px] text-ip-ink-3">{hint}</div>
    </div>
  );
}
