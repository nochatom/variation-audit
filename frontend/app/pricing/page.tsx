"use client";

import Link from "next/link";
import { useState } from "react";
import { Nav, SiteFooter } from "@/components/home/sections";
import { FaqList } from "@/components/faq/FaqList";
import { FAQ_PRICING } from "@/lib/faq";

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
  /** Announced but not yet shipped — rendered separately from `features` so a
   *  roadmap item can never be mistaken for something you can buy today. */
  roadmap?: string[];
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
    ],
    // Not features. SSO and advanced analytics aren't built, so they sat in
    // the bullet list beside things that work, with the same check mark —
    // selling something that doesn't exist. Kept visible but plainly marked,
    // because a buyer evaluating Enterprise is entitled to know the roadmap
    // without being told it has already shipped.
    roadmap: ["SSO", "Advanced analytics"],
  },
];


/* ---------------- page ---------------- */
export default function PricingPage() {
  const [interval, setInterval] = useState<"monthly" | "annual">("monthly");

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
            {/* Dropped "Most plans pay for themselves the first time we surface
                one you would have missed" — an unmeasurable claim, and the
                fifth place on this page the same argument was being made. */}
            <p className="mx-auto mt-4 max-w-xl text-[16px] leading-relaxed text-ip-ink-2">
              Start free on one project. Upgrade when the record shows it&apos;s worth it.
            </p>

            <div
              className="mt-10 inline-flex items-center gap-1 rounded-pill border border-ip-line bg-ip-card p-1 text-[13px] font-semibold"
              role="group"
              aria-label="Billing interval"
            >
              {/* Instant color-swap (not a sliding indicator): the two options
                  have very different widths, so a fixed 50% slider would
                  misalign. A crisp color change is the correct call here. */}
              <button
                aria-pressed={interval === "monthly"}
                className={`rounded-pill px-4 py-1.5 transition-colors duration-150 ease-out active:scale-[0.97] ${
                  interval === "monthly" ? "bg-ip-navy text-white" : "text-ip-ink-2 hover:text-ip-ink"
                }`}
                onClick={() => setInterval("monthly")}
              >
                Monthly
              </button>
              <button
                aria-pressed={interval === "annual"}
                className={`rounded-pill px-4 py-1.5 transition-colors duration-150 ease-out active:scale-[0.97] ${
                  interval === "annual" ? "bg-ip-navy text-white" : "text-ip-ink-2 hover:text-ip-ink"
                }`}
                onClick={() => setInterval("annual")}
              >
                Annual <span className={interval === "annual" ? "text-white/80" : "text-ip-recovery"}>· 2 months free</span>
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

        {/* Why it pays.

            The previous version of this section presented "Typical missed
            variation: AUD 3,000–20,000+" and "Break-even: often in month one"
            as stats, in the same grid as the real subscription price. Those
            figures aren't measured — there's no design-partner data behind
            them — and formatting an estimate like a finding lends it authority
            it hasn't earned. On a page selling financial rigour that is a
            liability, not a conversion lever.

            What replaces them is the part that's actually true and checkable:
            the price, and the reason the money is recoverable at all. The
            arithmetic is left to the reader, who knows their own variation
            values far better than we do. */}
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[1000px] px-6 py-20 sm:px-12">
            <div className="ip-card-lg p-8 sm:p-12">
              <p className="ip-label mb-4">Why this pays for itself</p>
              <h2 className="text-[clamp(1.6rem,3vw,2.1rem)] font-bold tracking-tight text-ip-ink">
                You already earned the money. The evidence is just scattered.
              </h2>
              <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-ip-ink-2">
                Variations get missed because the proof of them sits across contracts, RFIs, emails,
                site instructions and meeting minutes — not because the entitlement isn&apos;t real.
                VariationiQ reads that record so your commercial team can claim what was already
                earned, before a time-bar notice period closes the window.
              </p>
              <p className="mt-6 max-w-2xl text-[15px] font-semibold leading-relaxed text-ip-ink">
                Pro is AUD 149 a month. You know what one unclaimed variation is worth on your jobs
                better than we do — run it on a finished project and see what the record says.
              </p>
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
            {/* Rendered from lib/faq.ts, the same source as /faq, so an answer
                cannot drift between the two places a buyer reads it. */}
            <div className="mt-10">
              <FaqList items={FAQ_PRICING} />
            </div>
            <p className="mt-8 text-[14px] text-ip-ink-2">
              <Link href="/faq" className="font-semibold text-ip-ink underline underline-offset-4">
                See all questions
              </Link>{" "}
              — including how we handle your contracts and what the analysis can and can&apos;t claim.
            </p>
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
        // Prominent solid-navy pill (bg-ip-navy-fill is the design system's
        // designated fill for white-text badges — stays dark navy in both
        // themes) so it reads immediately against the card. Straddles the
        // card border; ring-4 in the page background carves a clean notch
        // where it crosses, shadow-ip-pop lifts it off the card.
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill bg-ip-navy-fill px-3.5 py-1 text-[11px] font-bold uppercase tracking-[0.09em] text-white shadow-ip-pop ring-4 ring-ip-bg">
          <span className="h-1.5 w-1.5 rounded-full bg-white" aria-hidden />
          Most Popular
        </span>
      )}
      <h3 className="text-lg font-bold tracking-tight text-ip-ink">{plan.label}</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ip-ink-3">{plan.tagline}</p>

      <div className="mt-6">
        {plan.tier === "enterprise" ? (
          <span className="text-2xl font-bold text-ip-ink">Contact Sales</span>
        ) : price === 0 ? (
          <>
            {/* "AUD 0", not "A$0": the Pro card beside this renders "AUD 149",
                and two currency conventions in one row of pricing cards is the
                kind of detail that costs credibility on a page about money. */}
            <span className="text-3xl font-bold tabular-nums text-ip-ink">AUD 0</span>
            <p className="mt-1 text-[12px] text-ip-ink-3">Forever</p>
          </>
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

      <ul className="mt-7 space-y-3 border-t border-ip-line pt-6">
        {plan.features.map((f) => (
          <FeatureRow key={f} feature={f} highlighted={plan.highlighted} />
        ))}
      </ul>

      {/* Separated from the feature list by a rule and its own label, so no
          roadmap item can be read as something included today. */}
      {plan.roadmap && plan.roadmap.length > 0 && (
        <div className="mt-5 border-t border-ip-line pt-4">
          <p className="ip-label mb-2">On the roadmap — not available yet</p>
          <p className="text-[13px] text-ip-ink-3">{plan.roadmap.join(" · ")}</p>
        </div>
      )}

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

/* One feature line. Every entry here is something the plan includes today —
   roadmap items render separately in PlanCard, so this no longer needs a
   second "coming later" state. */
function FeatureRow({ feature, highlighted }: { feature: string; highlighted?: boolean }) {
  return (
    <li className="flex items-start gap-3">
      <span
        className="mt-px grid h-5 w-5 shrink-0 place-items-center rounded-md bg-ip-recovery/12 text-ip-recovery"
        aria-hidden
      >
        <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      </span>
      <span className={`text-[13.5px] leading-5 ${highlighted ? "font-medium text-ip-ink" : "text-ip-ink-2"}`}>
        {feature}
      </span>
    </li>
  );
}
