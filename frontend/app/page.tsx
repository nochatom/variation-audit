import type { Metadata } from "next";
import { CtaBanner, Features, Hero, HowItWorks, Nav, ProductCapabilities, SiteFooter } from "@/components/home/sections";

export const metadata: Metadata = {
  title: "VariationIQ — Recover every unclaimed variation",
  description:
    "AI revenue recovery for Australian construction. VariationIQ scans contracts, RFIs, emails, site instructions and meeting minutes to find unclaimed variations, estimate recoverable value in AUD, and flag time-bar risk.",
};

export default function Home() {
  return (
    <div className="relative min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Nav />
      <Hero />
      <HowItWorks />
      <Features />
      <ProductCapabilities />
      <CtaBanner />
      <SiteFooter />
    </div>
  );
}
