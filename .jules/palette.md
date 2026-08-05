# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-08-05 - Accessible Custom Segmented Toggles & E2E Test Compatibility
**Learning:** In Tailwind-based design systems, custom segmented switch or toggle controls (like login/signup modes or billing intervals) are often implemented using native `<button>` arrays wrapped in generic containers. While aesthetically pleasing, they lack implicit keyboard selection states for assistive tech. Converting them to non-standard elements can break robust E2E test suites (like Playwright) targeting native buttons.
**Action:** Always wrap segmented `<button>` arrays in a container styled with `role="group"` and an `aria-label` describing the control, and toggle `aria-pressed` (true/false) on individual `<button>` elements to communicate active selection states without altering basic HTML tags or breaking test selectors.
