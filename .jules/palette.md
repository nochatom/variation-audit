# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-08-01 - Accessible Custom Segmented Toggles
**Learning:** When building custom segmented toggles using native `<button>` elements instead of radios (for styling flexibility), the component loses standard group association and selection state semantics for screen readers.
**Action:** Always use `role="group"` on the container with a descriptive `aria-label`, and `aria-pressed={isActive}` on each individual `<button>` element. This preserves implicit button roles and enables screen readers to announce the grouping, label, and toggle selection state correctly.
