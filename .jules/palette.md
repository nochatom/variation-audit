# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-08-04 - Accessible Segmented Switch / Toggle Controls
**Learning:** Custom segmented switch components (like billing interval or authentication mode selectors) often lack standard ARIA semantic definitions. Simple `div` wrapper containers of button lists can be confusing for screen readers and search crawlers without appropriate group markings.
**Action:** When structuring segmented switcher/toggle controls, define `role="group"` and a clear descriptive `aria-label` on the wrapper container, and pair individual `<button>` elements with `aria-pressed` state attributes. This approach keeps the native button accessible roles intact while preventing regressions on existing E2E testing selectors that look for button roles by name.
