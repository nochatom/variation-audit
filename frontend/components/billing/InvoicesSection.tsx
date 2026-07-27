"use client";

import { Card, EmptyState } from "@/components/ui";
import { Invoice } from "@/lib/billing/api";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

export function InvoicesSection({ invoices }: { invoices: Invoice[] }) {
  if (invoices.length === 0) {
    return (
      <EmptyState
        title="No invoices yet"
        body="You're currently on the Free plan, so there's no billing history. Invoices will appear here once you're on a paid plan."
      />
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-ip-line px-4 py-3">
        <h2 className="text-sm font-bold text-ip-ink">Invoices ({invoices.length})</h2>
      </div>
      <table className="w-full">
        <caption className="sr-only">Billing history</caption>
        <thead>
          <tr className="border-b border-ip-line">
            <th scope="col" className="ip-th">Period</th>
            <th scope="col" className="ip-th">Plan</th>
            <th scope="col" className="ip-th">Amount</th>
            <th scope="col" className="ip-th">Status</th>
            <th scope="col" className="ip-th text-right">Invoice</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((inv) => (
            <tr key={inv.id} className="ip-row">
              <td className="px-4 py-3 text-sm text-ip-ink-2">{fmtDate(inv.period_start)} – {fmtDate(inv.period_end)}</td>
              <td className="px-4 py-3 text-sm capitalize text-ip-ink-2">{inv.plan}</td>
              <td className="px-4 py-3 text-sm font-semibold text-ip-ink">{inv.currency} {inv.amount}</td>
              <td className="px-4 py-3 text-sm capitalize text-ip-ink-2">{inv.status}</td>
              <td className="px-4 py-3 text-right">
                {inv.hosted_invoice_url ? (
                  <a
                    href={inv.hosted_invoice_url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`Download invoice for ${fmtDate(inv.period_start)} – ${fmtDate(inv.period_end)}`}
                    className="btn-ghost px-2.5 py-1 text-xs"
                  >
                    Download PDF
                  </a>
                ) : (
                  <span className="text-[12px] text-ip-ink-3">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
