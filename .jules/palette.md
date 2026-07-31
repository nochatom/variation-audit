# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-07-31 - Segmented Toggle Switch Accessibility & Implicit Button Roles
**Learning:** Custom segmented toggle/switch controls (like login/signup modes, billing interval switches) built with simple button elements inside a styled div drop semantic group meaning for screen readers. Using standard ARIA tablist/tab patterns can break existing Playwright/testing selectors that expect standard buttons.
**Action:** Use `role="group"` on the container with an `aria-label` to group the controls, and `aria-pressed` on the individual `<button>` elements. This preserves the implicit button role (allowing name-based selectors to work perfectly) while correctly conveying the group context and toggle state to assistive technologies.
