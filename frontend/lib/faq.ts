/** The single FAQ source. Consumed by /faq (the full page) and by the pricing
 * page, which renders the `pricing` subset — so an answer can never drift
 * between the two places a buyer might read it. */
export type FaqGroup = "data" | "claims" | "how" | "billing";

export type FaqItem = {
  /** URL fragment. Stable — support links point at these, so treat a rename
   *  as a breaking change. */
  id: string;
  group: FaqGroup;
  q: string;
  a: string;
  /** Shown on the pricing page as well as /faq. */
  pricing?: boolean;
  /** Written, but the underlying behaviour has NOT been confirmed against the
   *  product. Nothing with this flag renders anywhere — see FAQ_DRAFTS below.
   *  Confirm the behaviour, delete the flag, and it goes live. A wrong answer
   *  about retention or model training is worse than no answer. */
  draft?: true;
};

export const FAQ_GROUP_LABEL: Record<FaqGroup, string> = {
  data: "Your data",
  claims: "Evidence & claims",
  how: "How it works",
  billing: "Plans & billing",
};

export const FAQ_GROUP_ORDER: FaqGroup[] = ["data", "claims", "how", "billing"];

const ITEMS: FaqItem[] = [
  // ---------------- Your data ----------------
  {
    id: "who-can-see",
    group: "data",
    q: "Who can see our contracts and correspondence?",
    a:
      "Only people you invite to your organisation. Projects, documents and analyses are " +
      "scoped to your organisation and are not visible to other customers. Billing and audit " +
      "endpoints are restricted to organisation admins.",
    pricing: true,
  },
  {
    id: "where-stored",
    group: "data",
    q: "Where is our data stored?",
    a: "In Australia — ap-southeast-2 (Sydney). Your project record does not leave the region.",
    pricing: true,
  },
  {
    id: "model-training",
    group: "data",
    q: "Do you train AI models on our documents?",
    a:
      "No. Customer data and uploaded documents are never used to train AI models. Each analysis " +
      "is isolated to your workspace — your documents are read to produce your result and nothing " +
      "else.",
    pricing: true,
  },
  {
    id: "data-on-downgrade",
    group: "data",
    q: "What happens to my data if I downgrade to the Free plan?",
    a:
      "Your projects and documents remain safe. If you exceed the Free plan limits after " +
      "downgrading, your workspace becomes read-only until you upgrade or reduce usage. No " +
      "projects or documents are automatically deleted because of a downgrade.",
    pricing: true,
  },

  // ---------------- Evidence & claims ----------------
  {
    id: "legal-advice",
    group: "claims",
    q: "Is this legal advice?",
    a:
      "No. VariationiQ reads your project record and shows you what it finds. Whether to claim, " +
      "how to frame entitlement, and what a clause means in your circumstances are decisions for " +
      "your commercial and legal team.",
    pricing: true,
  },
  {
    // Renamed from "hold-up" while it was still a draft — never rendered, so
    // no link can break. The id now matches what the question actually asks.
    id: "citations",
    group: "claims",
    q: "Does VariationiQ cite the source documents for its findings?",
    a:
      "Yes. Every finding is linked to the relevant source document and supporting passage " +
      "whenever available, so you can verify the evidence behind each result.",
  },
  {
    id: "time-bars",
    group: "claims",
    q: "Does VariationiQ identify notice periods and potential time bars?",
    a:
      "Yes. When supported by the uploaded contract and project documents, VariationiQ highlights " +
      "relevant notice periods and potential time-bar risks associated with detected variations.",
  },
  {
    id: "missed-something",
    group: "claims",
    q: "What if it misses a variation, or flags one that isn't real?",
    a:
      "VariationiQ is designed to accelerate document review, not replace professional judgment. " +
      "Every finding includes supporting evidence from the source documents whenever possible, " +
      "and nothing is submitted or acted on automatically. You remain in control — review each " +
      "finding, accept or dismiss it, and make the final decision before taking any contractual " +
      "or commercial action.",
    pricing: true,
  },

  // ---------------- How it works ----------------
  {
    id: "what-is-analysis",
    group: "how",
    q: "What counts as an AI analysis?",
    a:
      "One analysis run is one full pass over a project's contract, RFIs, site instructions, " +
      "meeting minutes and comms to detect and value variations. You can re-run analysis as the " +
      "project record grows.",
    pricing: true,
  },
  {
    id: "file-types",
    group: "how",
    q: "Which file types does VariationiQ support?",
    a:
      "VariationiQ supports PDF, DOCX, XLSX, XLS, CSV, and common image formats such as PNG and " +
      "JPG. Support for additional formats will continue to expand over time.",
    pricing: true,
  },
  {
    id: "roi",
    group: "how",
    q: "How does the ROI actually work?",
    a:
      "VariationiQ doesn't create revenue — it surfaces revenue you already earned but haven't " +
      "claimed. Pro is AUD 149/month, so the question is simply whether a year of that is worth " +
      "less than the variations currently going unclaimed on your projects. Start on the Free " +
      "plan with one finished job and judge it against your own numbers rather than ours.",
    pricing: true,
  },

  // ---------------- Plans & billing ----------------
  {
    id: "over-limits",
    group: "billing",
    q: "What happens if I go over my plan's limits?",
    a:
      "Billing tells you which limit is binding and what it blocks. Monthly limits — analyses and " +
      "documents — reset on the first of the month. Project slots don't reset; archiving frees " +
      "one. Nothing is deleted when you hit a cap.",
    pricing: true,
  },
  {
    id: "seats",
    group: "billing",
    q: "Can I add more than 15 seats on Pro?",
    a:
      "Yes. Pro includes 15 seats; additional seats beyond that are billed as seat overage on your " +
      "existing subscription, so your team isn't blocked from growing.",
    pricing: true,
  },
  {
    id: "interval",
    group: "billing",
    q: "Can I switch between monthly and annual billing?",
    a:
      "Yes — annual billing is roughly 2 months free compared to paying monthly. Use \"Manage " +
      "billing\" in Settings to change your billing interval, or contact us if you need help " +
      "switching.",
    pricing: true,
  },
  {
    id: "trial",
    group: "billing",
    q: "Do you offer a free trial of Pro?",
    a:
      "The Free plan itself has no time limit — it's scoped to 1 project so you can fully test " +
      "variation detection on a real project before upgrading, rather than a countdown trial.",
    pricing: true,
  },
  {
    id: "enterprise-price",
    group: "billing",
    q: "What does Enterprise pricing look like?",
    a:
      "Enterprise is custom-priced around your number of projects, seats, and support needs. " +
      "Contact sales and we'll put together a quote.",
    pricing: true,
  },
];

/** Everything publishable. Drafts are excluded here rather than filtered at
 *  each call site, so an unconfirmed answer cannot reach a page by accident. */
export const FAQ: FaqItem[] = ITEMS.filter((i) => !i.draft);

/** Written but unconfirmed. Not exported into any page — kept so the wording
 *  isn't lost while the behaviour is being checked. */
export const FAQ_DRAFTS: FaqItem[] = ITEMS.filter((i) => i.draft);

export const FAQ_PRICING: FaqItem[] = FAQ.filter((i) => i.pricing);

export function faqByGroup(items: FaqItem[]): { group: FaqGroup; items: FaqItem[] }[] {
  return FAQ_GROUP_ORDER.map((group) => ({
    group,
    items: items.filter((i) => i.group === group),
  })).filter((g) => g.items.length > 0);
}
