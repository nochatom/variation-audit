import type { Metadata } from "next";
import { Nav, SiteFooter } from "@/components/home/sections";
import { FaqList } from "@/components/faq/FaqList";
import { FAQ } from "@/lib/faq";

export const metadata: Metadata = {
  title: "FAQ — VariationiQ",
  description:
    "How VariationiQ handles your project record, what it can and can't claim, and how plans work.",
};

export default function FaqPage() {
  return (
    <div className="relative min-h-screen bg-ip-bg font-ip text-ip-ink">
      <Nav />
      <main>
        <section className="border-b border-ip-line">
          <div className="mx-auto max-w-[880px] px-6 py-20 sm:px-12">
            <p className="ip-label text-ip-ink-3">Help</p>
            <h1 className="mt-3 max-w-[16ch] text-[clamp(2rem,4.2vw,2.9rem)] font-bold leading-[1.08] tracking-tight text-ip-ink">
              Questions, answered.
            </h1>
            <p className="mt-4 max-w-[54ch] text-[17px] leading-relaxed text-ip-ink-2">
              Everything about how VariationiQ handles your project record, what it can and
              can&apos;t claim, and how plans work.
            </p>
          </div>
        </section>

        <section>
          <div className="mx-auto max-w-[880px] px-6 py-16 sm:px-12">
            {/* Grouped and filterable here — sixteen questions get scanned, not
                read. The pricing page renders the same source unfiltered. */}
            <FaqList items={FAQ} grouped filterable />

            <div className="mt-14 flex flex-wrap items-center gap-4 rounded-2xl border border-ip-line bg-ip-card p-6">
              <p className="flex-1 text-[14px] text-ip-ink-2">
                <strong className="font-semibold text-ip-ink">Still stuck?</strong> If your question
                isn&apos;t here, it should be. Tell us and we&apos;ll add it.
              </p>
              <a href="mailto:hello@variationiq.com" className="btn-navy px-5 py-2.5 text-[14px]">
                Email us
              </a>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
