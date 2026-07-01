// Applies the saved Ironclad theme (light/dark) before paint, so app/login
// pages never flash the wrong theme. Landing ignores the `dark` class entirely.
// Served as a same-origin static file (not inline) so the CSP can use
// script-src 'self' without 'unsafe-inline'.
(function () {
  try {
    var t = localStorage.getItem("va_theme");
    if (t === "dark") document.documentElement.classList.add("dark");
  } catch (e) {
    /* localStorage unavailable — fall back to default (light) */
  }
})();
