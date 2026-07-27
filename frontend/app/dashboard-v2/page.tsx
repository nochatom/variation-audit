/**
 * VariationIQ — Dashboard, design reference.
 *
 * The master screen for the 10-screen platform: the shell, grid, type scale and
 * component styles established here are reused unchanged elsewhere, and only
 * this file's main-area content varies per screen.
 *
 * Static spec content by design. This route deliberately sits OUTSIDE app/app/
 * so it renders the reference shell (components/v2/Chrome.tsx) rather than the
 * shipping AppChrome, and needs no auth or AppProvider context. The live
 * dashboard at /app/dashboard is untouched.
 */
import type { Metadata } from "next";
import { VqChrome } from "@/components/v2/Chrome";
import {
  BarChart,
  Button,
  Card,
  CardTitle,
  FilterChips,
  MetricCard,
  StatusPill,
  TextLink,
  confidenceBand,
} from "@/components/v2/ui";

export const metadata: Metadata = {
  title: "Dashboard — VariationIQ",
};

/** AUD, no cents — these are claim estimates, not invoiced amounts. */
const aud = (n: number) => `$${n.toLocaleString("en-AU")}`;

const FINDINGS = [
  {
    finding: "Additional structural steel not in tender scope",
    project: "Northgate Logistics Hub",
    type: "Scope Change",
    value: 184_500,
    confidence: 94,
    documents: 7,
    date: "12 Jul",
  },
  {
    finding: "Client-directed slab thickening — SI-142",
    project: "Riverside Apartments Stage 2",
    type: "Site Instruction",
    value: 96_200,
    confidence: 91,
    documents: 4,
    date: "11 Jul",
  },
  {
    finding: "Extended preliminaries from 18-day access delay",
    project: "Port Melbourne Warehouse",
    type: "Delay Event",
    value: 237_800,
    confidence: 87,
    documents: 11,
    date: "9 Jul",
  },
  {
    finding: "Revised facade glazing spec after Rev C drawings",
    project: "Northgate Logistics Hub",
    type: "Design Change",
    value: 62_400,
    confidence: 79,
    documents: 5,
    date: "8 Jul",
  },
  {
    finding: "Out-of-hours works requested via email 04/07",
    project: "Collins St Fitout",
    type: "Additional Work",
    value: 28_900,
    confidence: 71,
    documents: 3,
    date: "5 Jul",
  },
];

const VALUE_BY_TYPE = [
  { name: "Scope Change", label: "$912k", value: 912 },
  { name: "Delay Event", label: "$784k", value: 784 },
  { name: "Design Change", label: "$621k", value: 621 },
  { name: "Additional Work", label: "$530k", value: 530 },
];

const ACTIVITY = [
  { text: "Analysis completed", meta: "Riverside Apartments Stage 2 · 2h ago", d: "M20.5 12a8.5 8.5 0 11-8.5-8.5A8.5 8.5 0 0120.5 12zM8.5 12.2l2.4 2.4 4.6-4.8" },
  { text: "14 documents uploaded", meta: "Collins St Fitout · 5h ago", d: "M12 16.5V4.5M7.5 9L12 4.5 16.5 9M4.5 15v3.5a1 1 0 001 1h13a1 1 0 001-1V15" },
  { text: "Report generated", meta: "Northgate Logistics Hub · Yesterday", d: "M7 3.5h6.5L18 8v12.5a1 1 0 01-1 1H7a1 1 0 01-1-1v-16a1 1 0 011-1zM13 3.5V8h5M9 13.5h6M9 17h4" },
  { text: "Sarah Chen joined the organisation", meta: "2 days ago", d: "M13.5 8a3.5 3.5 0 11-7 0 3.5 3.5 0 017 0zM4 19.5c0-3.3 2.7-5.5 6-5.5 1.2 0 2.3.3 3.2.8M17 14v5.5M14.2 16.7h5.6" },
];

const DocIcon = ({ size = 16 }: { size?: number }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.9}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className="shrink-0"
  >
    <path d="M7 3.5h6.5L18 8v12.5a1 1 0 01-1 1H7a1 1 0 01-1-1v-16a1 1 0 011-1zM13 3.5V8h5" />
  </svg>
);

export default function DashboardV2() {
  return (
    <VqChrome title="Dashboard" subtitle="Across 12 active projects" active="Dashboard">
      {/* ------------------------------------------------- 1. metric row --- */}
      <div className="col-span-3">
        <MetricCard label="Potential Recoverable Value" value={aud(2_847_300)} accent>
          <span className="vq-num font-medium text-vq-high">+{aud(312_000)}</span> this month
        </MetricCard>
      </div>
      <div className="col-span-3">
        <MetricCard label="Variations Detected" value="68">
          <span className="vq-num">23</span> awaiting review
        </MetricCard>
      </div>
      <div className="col-span-3">
        <MetricCard label="Documents Analysed" value="4,912">
          across <span className="vq-num">12</span> projects
        </MetricCard>
      </div>
      <div className="col-span-3">
        <MetricCard label="Average Confidence" value="82%">
          of detected findings
        </MetricCard>
      </div>

      {/* --------------------------------- 2a. findings queue (12 cols) ---
          Full width, not the spec's 8/12: the table needs 1235px of natural
          content and an 8-col span offers 747px. See vq.css for the measured
          breakdown. The three rail cards follow beneath, 4 columns each. */}
      <Card flush className="col-span-12">
        <div className="p-6 pb-4">
          <CardTitle id="vq-findings">Findings awaiting review</CardTitle>
        </div>

        <FilterChips
          label="Filter findings"
          selected="All"
          options={["All", "High confidence", "High value", "New this week"]}
        />

        <div className="vq-tablewrap">
          <table className="vq-table" aria-labelledby="vq-findings">
            <thead>
              <tr>
                <th scope="col" className="vq-col-finding">Finding</th>
                <th scope="col" className="vq-col-project">Project</th>
                <th scope="col">Type</th>
                <th scope="col" className="vq-num-col">Est. Value</th>
                {/* "Conf." not "Confidence": at 12px/0.06em the full word is
                    104px wide to label a 46px pill, and that surplus was taken
                    straight out of the finding titles. The pill's % is
                    self-describing; the full word stays for screen readers. */}
                <th scope="col">
                  <abbr title="Confidence" className="no-underline">Conf.</abbr>
                </th>
                <th scope="col">Evidence</th>
                <th scope="col">Date</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {FINDINGS.map((f) => (
                <tr key={f.finding}>
                  <td className="vq-cell-truncate font-medium text-vq-ink" title={f.finding}>
                    {f.finding}
                  </td>
                  <td className="vq-cell-truncate text-vq-ink-2" title={f.project}>
                    {f.project}
                  </td>
                  <td className="text-vq-ink-2">{f.type}</td>
                  <td className="vq-num-col vq-num font-medium text-vq-ink">{aud(f.value)}</td>
                  <td>
                    <StatusPill band={confidenceBand(f.confidence)}>{f.confidence}%</StatusPill>
                  </td>
                  <td>
                    <a
                      href="#"
                      className="inline-flex items-center gap-1.5 text-sm text-vq-navy hover:underline"
                    >
                      <span className="text-vq-ink-2">
                        <DocIcon />
                      </span>
                      <span className="vq-num">{f.documents}</span> documents
                    </a>
                  </td>
                  <td className="vq-num text-vq-ink-2">{f.date}</td>
                  <td className="vq-num-col">
                    <TextLink
                      className="vq-row-action"
                      aria-label={`Review: ${f.finding}`}
                    >
                      Review
                    </TextLink>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="border-t border-vq-line px-6 py-4">
          <TextLink>View all 23 findings</TextLink>
        </div>
      </Card>

      {/* ------------------------------------ 2b. supporting cards (4+4+4) ---
          `self-start` on each: grid items stretch by default, which left the
          shortest card padded with dead space to match its tallest sibling. */}
      <Card className="col-span-4 self-start">
        <CardTitle>Value by variation type</CardTitle>
        <BarChart rows={VALUE_BY_TYPE} />
      </Card>

      <Card className="col-span-4 self-start">
        <CardTitle>Recent activity</CardTitle>
        <ul className="mt-6 flex flex-col">
            {ACTIVITY.map((a, i) => (
              <li key={a.text} className="relative flex gap-3 pb-4 last:pb-0">
                {i < ACTIVITY.length - 1 && (
                  <span aria-hidden className="absolute bottom-0 left-[11px] top-6 w-px bg-vq-line" />
                )}
                <span className="relative z-10 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-vq-line bg-vq-bg text-vq-ink-2">
                  <svg
                    viewBox="0 0 24 24"
                    width={14}
                    height={14}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                  >
                    <path d={a.d} />
                  </svg>
                </span>
                <div className="min-w-0 pt-0.5">
                  <p className="text-[13px] leading-snug text-vq-ink">{a.text}</p>
                  <p className="mt-0.5 text-[12px] text-vq-ink-2">{a.meta}</p>
                </div>
              </li>
          ))}
        </ul>
      </Card>

      <Card className="col-span-4 self-start">
        <CardTitle>Start a new analysis</CardTitle>
        <p className="mb-6 mt-2 max-w-[34ch] text-[13px] text-vq-ink-2">
          Upload contract documents, drawings and correspondence to detect unclaimed variations.
        </p>
        <Button>
          <svg
            viewBox="0 0 24 24"
            width={20}
            height={20}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M12 5.5v13M5.5 12h13" />
          </svg>
          New Project
        </Button>
      </Card>
    </VqChrome>
  );
}
