// Interface web todo-cli : aucun script en ligne (CSP). Thème clair/sombre selon le système, confirmations.
(function () {
  var sombre = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
  function theme() { document.documentElement.setAttribute("data-bs-theme", sombre && sombre.matches ? "dark" : "light"); }
  theme();
  if (sombre && sombre.addEventListener) sombre.addEventListener("change", theme);
  document.addEventListener("change", function (e) {
    if (e.target.hasAttribute("data-autosubmit")) e.target.form.submit();
  });
  document.addEventListener("submit", function (e) {
    var message = e.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) e.preventDefault();
  });
})();
