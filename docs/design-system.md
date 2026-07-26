# Ironclad Precision — VariationIQ Design System

**Status:** authoritative for the application UI.
**Source of truth:** the code, not this file. Tokens live in
`frontend/app/globals.css` (`:root` / `.dark` custom properties) and are bound
to utilities in `frontend/tailwind.config.ts`. This document describes what is
there; if the two disagree, the code wins and this file is the bug.

> **Do not confuse this with `frontend/DESIGN.md`.** That file is a tracked
> Linear-analysis artifact produced by `npx getdesign@latest add linear.app`.
> It describes a near-black marketing palette (`#010102` / `#5e6ad2`) that the
> application does **not** use. It is not this system.

---

## 1. Principles

1. **Data density over decoration.** Screens are for deciding, not browsing.
   No gradients, no marketing effects, no ornamental motion.
2. **Colour carries meaning, never mood.** Every non-neutral colour in the
   palette has exactly one job (below). A colour used decoratively destroys the
   signal the same colour carries elsewhere.
3. **One workflow per page.** The Dashboard is KPIs plus navigation — never an
   everything-screen.
4. **Confidence is not a status.** Model confidence renders on a neutral navy
   scale, never in success/warning/error colours, so a low-confidence detection
   is never misread as a rejected one.

---

## 2. Colour tokens

Defined as space-separated RGB triples so Tailwind can apply alpha
(`rgb(var(--ip-ink) / <alpha-value>)`). Both themes are first-class; `.dark` on
`<html>` is toggled by `lib/use-theme.ts`.

### Surfaces and lines

| Token | Utility | Light | Dark | Role |
|---|---|---|---|---|
| `--ip-bg` | `bg-ip-bg` | `#f7f9ff` | `#0a0d13` | Page canvas |
| `--ip-card` | `bg-ip-card` | `#ffffff` | `#12161f` | Card / panel surface |
| `--ip-card-2` | `bg-ip-card-2` | `#eef4ff` | `#181d28` | Hover / raised surface |
| `--ip-card-3` | `bg-ip-card-3` | `#e5effe` | `#1f2531` | Nested surface |
| `--ip-line` | `border-ip-line` | `#dfe4ee` | `#2a3140` | Default hairline |
| `--ip-line-strong` | `border-ip-line-strong` | `#c5c6cd` | `#3c4456` | Input borders, emphasis |

### Ink (text)

| Token | Utility | Light | Dark | Role |
|---|---|---|---|---|
| `--ip-ink` | `text-ip-ink` | `#121c27` | `#eef1f7` | Primary text, headings |
| `--ip-ink-2` | `text-ip-ink-2` | `#45474d` | `#aab2c2` | Secondary text |
| `--ip-ink-3` | `text-ip-ink-3` | `#5c5e65` | `#7c8494` | Tertiary, labels, captions |

`--ip-ink-3` was deliberately darkened in light mode (from `#75777d`) to clear
WCAG AA at small sizes. Do not lighten it back.

### Accents — each has exactly one job

| Token | Utility | Light | Dark | **Only** used for |
|---|---|---|---|---|
| `--ip-navy` | `text-ip-navy` | `#051125` | `#93a8e0` | Links, icons, evidence/confidence scale. Adaptive: lightens in dark. |
| `--ip-navy-fill` | `bg-ip-navy-fill` | `#051125` | `#33446b` | Solid fills behind white text (buttons, badges) |
| `--ip-orange` | `bg-ip-orange` | `#ff7a26` | `#ff8a3d` | **Non-text accents only**: status dots, borders, tints, focus rings, icons |
| `--ip-orange-2` | `text-ip-orange-2` | `#9e4300` | `#ffb27a` | Orange **text** (adapts per theme) |
| `--ip-orange-fill` | `bg-ip-orange-fill` | `#9e4300` | `#9e4300` | Solid fill behind **white text** (`.btn-orange`); fixed in both themes |
| `--ip-recovery` | `text-ip-recovery` | `#086e2d` | `#3ddc78` | Recovered / recoverable money values |
| `--ip-risk` | `text-ip-risk` | `#ba1a1a` | `#ff6b5e` | Errors, rejections, time-bar breach |
| `--ip-risk-bg` | `bg-ip-risk-bg` | `#ffdad6` | `#3a1411` | Tint behind risk text |

**Construction Orange is the scarcest resource in this system.** It marks the
one action that matters on a screen, or an expiring time bar. If two orange
things compete on one page, one of them is wrong.

**Orange splits three ways by job — pick by what sits on top:**

| If the orange is… | Use | Why |
|---|---|---|
| behind white text (a button) | `--ip-orange-fill` | `#ff7a26` under white is 2.60:1 — fails AA |
| the text itself | `--ip-orange-2` | theme-adaptive, stays legible on both surfaces |
| carrying nothing (dot, border, tint, ring) | `--ip-orange` | full-strength brand accent, no contrast burden |

Same brand, three roles. `#ff7a26` is untouched everywhere it isn't obscuring
a label — which is why the identity reads unchanged on screen.

---

## 3. Typography

- **Family:** Public Sans, via `font-ip` (`--font-public-sans`, self-hosted in
  `app/fonts/`). Self-hosted deliberately — the production build never depends
  on fetching Google Fonts.
- **Tracking:** body carries `-0.006em`; `h1/h2/h3` carry `-0.021em` with
  `text-wrap: balance`.
- **Numerals:** `.tabular-nums` wherever figures are compared or aligned —
  dashboards and money columns must never have digits that dance.

| Role | Class | Notes |
|---|---|---|
| Field label | `.ip-label` | 11px, semibold, uppercase, `0.06em`, ink-3 |
| Table header | `.ip-th` | 12px, semibold, uppercase, `0.04em`, ink-3 |
| Body | default | 14px in app chrome |

---

## 4. Component primitives

Defined in `globals.css` under `@layer components`.

| Class | Composition |
|---|---|
| `.ip-card` | `rounded-lg`, `border-ip-line`, `bg-ip-card`, `shadow-ip-card` |
| `.ip-card-lg` | as above, `rounded-xl` |
| `.ip-card-interactive` | `.ip-card` + hover lift (`-2px`) and `border-ip-line-strong`; **opt-in only for genuinely clickable cards** — a hover affordance on a static stat card is a lie |
| `.btn-navy` | `bg-ip-navy-fill`, white text — default action |
| `.btn-orange` | `bg-ip-orange-fill`, white text — primary action; hover `brightness(1.15)` (see §6) |
| `.btn-ghost` | `border-ip-line-strong`, `bg-ip-card`, navy text — tertiary |
| `.ip-input` | `border-ip-line-strong`, orange focus ring at 25% |
| `.ip-th` / `.ip-row` | table header cell / row separator |

**Motion:** all interactive transitions run 160–200ms on
`--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`. Buttons scale to `0.97` on
`:active`. The built-in CSS easings are too weak to read as intentional.

**Focus:** buttons take `ring-2 ring-ip-navy/40` with `ring-offset-2`. Focus is
never removed — only restyled.

### React primitives (`components/ui.tsx`)

`PageHeader` · `Card` · `StatCard` · `Chip` · `ConfidenceBar` · `TimeBarFlag` ·
`EmptyState` · `ErrorNote` · `InfoNote` · `Spinner` · `statusTone` · `fmtDate`

`statusTone(status)` is the single mapping from domain status to colour:

| Status | Tone |
|---|---|
| `confirmed`, `completed`, `succeeded` | `recovery` |
| `rejected`, `failed` | `risk` |
| everything else | `navy` |

`ConfidenceBar` renders 5 segments filled on `bg-ip-navy` against
`bg-ip-line-strong` — **navy, never status colours**, per §1.4.

---

## 5. Accessibility audit

Measured from the live token values (WCAG 2.1 relative luminance). AA requires
4.5:1 for normal text, 3:1 for large text and UI components.

| Pair | Light | Dark | Verdict |
|---|---|---|---|
| ink on page bg | 16.34:1 | 17.19:1 | Pass |
| ink on card | 17.20:1 | 16.00:1 | Pass |
| ink-2 on card | 9.29:1 | 8.49:1 | Pass |
| ink-3 on card | 6.47:1 | 4.81:1 | Pass |
| ink-3 on page bg | 6.15:1 | 5.17:1 | Pass |
| navy link on card | 18.86:1 | 7.69:1 | Pass |
| recovery green on card | 6.41:1 | 10.09:1 | Pass |
| risk red on risk-bg | 5.00:1 | 5.84:1 | Pass |
| white on `.btn-navy` | 18.86:1 | 9.63:1 | Pass |
| white on `.btn-orange` (fill) | 6.45:1 | 6.45:1 | Pass |
| white on `.btn-orange` :hover | 5.18:1 | 5.18:1 | Pass |
| orange-2 text on card | 6.45:1 | 7.72:1 | Pass |
| unread-count badge on tint | 5.75:1 | — | Pass |

Every pairing now clears AA. The `.btn-orange` and badge figures were verified
in a live browser (computed styles, both themes), not only by calculation.

---

## 6. The orange contrast fix (applied)

**The defect.** White on Construction Orange `#ff7a26` measured **2.60:1** —
below the 4.5:1 normal-text threshold and below even the 3:1 large-text/UI
threshold. The dark variant `#ff8a3d` was worse at 2.35:1. It affected all
**16** `.btn-orange` call sites, which are the primary calls to action: "Run
analysis", "Create project", "Save", "Review variations", document upload.

There was also a tell: `.btn-orange:hover` swapped *to* `--ip-orange-2`
(`#9e4300`, 6.45:1), so the button was legible **only while hovered**. The
right colour was already in the palette, applied to the wrong state.

**The fix.** Split orange by job (§2) and promote the existing `#9e4300` to the
resting fill via a new *variable* — `--ip-orange-fill` — holding an existing
*value*. No new colour enters the palette. This mirrors the `--ip-navy` /
`--ip-navy-fill` split already in the system: an adaptive token for text and
icons, a fixed token for fills that sit behind white text.

Hover brightens the same fill (`filter: brightness(1.15)` → ~`#b64d00`,
5.18:1) rather than swapping tokens. The light ramp has no darker orange to
step toward, and stepping *up* to `#ff7a26` is exactly what caused the original
bug.

**Also changed:** the unread-count badge in `chrome.tsx` rendered its number in
`--ip-orange` on a 12% orange tint — **2.32:1**. Moved to `--ip-orange-2`
(**5.75:1**), matching the `Chip` orange tone in `ui.tsx`.

**Deliberately unchanged:** `#ff7a26` still owns every non-text job — the three
notification status dots, all borders (`border-ip-orange/30`), all tints
(`bg-ip-orange/12`), and the `.ip-input` focus ring. The brand accent is
untouched wherever it isn't obscuring a label.

### Residual items (not defects under the current scope)

- **Two meaningful icons** use `--ip-orange` at 2.60:1 in light: the
  `TriangleAlert` on Documents and the `Lock` on Reports. WCAG 1.4.11 asks 3:1
  of non-text content that conveys meaning. Both sit beside explanatory text,
  so the meaning is not colour-dependent — but `--ip-orange-2` would clear it
  if you want strict conformance.
- **The `.ip-input` focus ring** is `--ip-orange` at 25% opacity. Focus
  indicators fall under the same 3:1 rule. It is paired with a solid
  `border-ip-orange` change, so focus is not signalled by the ring alone.
- **Dark-theme button boundary:** the `#9e4300` fill against the dark card
  (`#12161f`) is 2.81:1. The 6.45:1 white label makes the control unmistakable,
  so this is not a 1.4.11 failure in practice — noted for completeness.

---

## 7. Rules for new UI

- Build from the primitives in §4. If you need a new one, add it to
  `globals.css` — do not inline a one-off variant in a page.
- Never hardcode a hex value in a component. If a colour you need does not
  exist as a token, that is a design decision, not a styling shortcut.
- Both themes are shipped. Anything you add must be checked in light **and**
  dark; the token indirection makes this free if you use tokens, and impossible
  if you don't.
- Orange is not available for emphasis. See §2.
- Confidence never uses status colour. See §1.4.
