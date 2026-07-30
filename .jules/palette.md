# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-07-27 - Custom Inline Toggle Toggles Accessibility
**Learning:** Inline toggle buttons mimicking tab controls (like choosing login/signup modes or billing intervals) are visually intuitive but entirely opaque to screen readers if they are rendered as generic container-button flows. While `role="tablist"` is standard for tabs, changing the role from button to tab breaks existing E2E test selectors expecting buttons. Using `role="group"` with a descriptive `aria-label` and `aria-pressed` on the nested standard buttons offers the perfect balance—it makes the custom toggle highly accessible to screen readers as toggle buttons while maintaining full compatibility with the existing test suite's button queries.
**Action:** Wrap custom segment/inline toggle controls in containers with `role="group"` and a descriptive `aria-label`, and annotate toggle options with `aria-pressed` rather than changing roles to `tab`.
