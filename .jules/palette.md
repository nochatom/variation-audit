# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-08-02 - Accessible Custom Segmented Toggles and Switching Controls
**Learning:** Custom styled segmented switch/toggle controls (e.g., login/signup modes, monthly/annual pricing intervals) are often implemented using div containers and standard buttons, which strip necessary screen reader context and make it difficult for assistive technologies to detect state.
**Action:** Always wrap custom segmented switches in a container with `role="group"` and a clear `aria-label` describing the control group. Ensure individual `<button>` elements within utilize `aria-pressed` indicating their selection state. This perfectly preserves implicit button roles and prevents breaking automated E2E selectors that query by button name.
