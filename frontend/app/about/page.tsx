import type { Metadata } from "next";
import { Nav, SiteFooter } from "@/components/home/sections";

export const metadata: Metadata = {
  title: "About — VariationiQ",
  description: "VariationiQ helps Australian construction companies recover variation revenue they'd otherwise leave on the table.",
};

export default function AboutPage() {
  return (
    <div className="relative min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Nav />
      <main className="mx-auto max-w-[720px] px-6 py-20 sm:px-12 lg:px-16">
        <p className="ip-label text-ip-ink-3">About</p>
        <h1 className="mt-2 text-[clamp(1.9rem,3.6vw,2.8rem)] font-bold tracking-tight text-ip-ink">
          Built for the paperwork nobody has time to chase.
        </h1>
        <div className="mt-8 space-y-5 text-[15px] leading-relaxed text-ip-ink-2">
          <p>
            Variations get missed constantly on construction projects — not because the entitlement isn&apos;t there,
            but because the evidence for it is scattered across contracts, RFIs, emails, site instructions and
            meeting minutes, and nobody has the hours to read all of it before a time-bar clause closes the window.
          </p>
          <p>
            VariationiQ reads that project record with AI, cross-references it against the contract, and surfaces
            the variations that are supported by real evidence — with the source quoted, a recoverable value estimate
            in AUD, and a flag when a time-bar deadline is at risk. Every finding is reviewed and confirmed by a
            person before it&apos;s treated as real; the tool finds candidates, it doesn&apos;t make claims on its own.
          </p>
          <p>
            We&apos;re scoped to Australian commercial construction — general contractors, builders, and electrical,
            plumbing, HVAC and fire protection subcontractors — because the time-bar and security-of-payment regimes
            here are specific enough that a generic tool wouldn&apos;t get the detail right.
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
