# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.
