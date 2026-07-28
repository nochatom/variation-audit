import type { Metadata } from "next";
import { CtaBanner, Features, Hero, HowItWorks, Nav, SiteFooter } from "@/components/home/sections";

export const metadata: Metadata = {
  title: "VariationiQ — Recover every unclaimed variation",
  description:
    "AI revenue recovery for Australian construction. VariationiQ scans contracts, RFIs, emails, site instructions and meeting minutes to find unclaimed variations, estimate recoverable value in AUD, and flag time-bar risk.",
};

export default function Home() {
  return (
    <div className="relative min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Nav />
      <Hero />
      <HowItWorks />
      <Features />
      <CtaBanner />
      <SiteFooter />
    </div>
  );
}
