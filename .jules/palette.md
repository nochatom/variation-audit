# Palette's UX Journal

This journal documents critical UX and accessibility learnings from working on the VariationIQ user interface.

## 2026-07-26 - Canonical Form Accessibility & Input-Label Pairing
**Learning:** Legacy UI components and dynamically rendered forms can easily drop semantic relationships (like `htmlFor` and `id`) in React, which breaks form field focus and makes screen readers fail to associate labels with inputs.
**Action:** Always ensure that all interactive forms explicitly couple `<label>` elements with their corresponding inputs using unique `id` and `htmlFor` attributes, especially for high-importance workflows like login, forgot password, and destructive action modals.

## 2026-07-27 - Custom Topbar Dropdowns and Accessible WAI-ARIA Menu Patterns
**Learning:** Custom interactive components like the user profile button and dropdown overlays can easily miss core ARIA menu patterns (such as dynamic `aria-expanded`, `aria-haspopup="menu"`, and correct menu/menuitem roles), which leaves assistive technology completely blind to the existence, state, and options of the dropdown.
**Action:** When building interactive header/topbar menus, always assign standard WAI-ARIA roles (`role="menu"` on the container and `role="menuitem"` on links/buttons), ensure the trigger button manages both `aria-expanded` and `aria-haspopup`, provide dynamic screen reader labels, and implement standard `Escape` and `pathname` listeners to close the dropdown.
