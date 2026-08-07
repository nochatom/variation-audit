# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-07-28 - Custom Segmented Toggle and Switch Group Accessibility
**Learning:** Custom toggle groups built using adjacent `<button>` elements lack structural relationships out-of-the-box in screen readers, leading to poor semantic flow and making it difficult for users with assistive technologies to discover which options are grouped together or active.
**Action:** Always wrap custom segmented toggles in a container with `role="group"` and an explicit, clear `aria-label` describing the control group (e.g. "Billing interval", "Authentication mode"). Use `aria-pressed` on the nested button components to natively convey active state without resorting to redundant visual labels or breaking existing automated test selectors.
