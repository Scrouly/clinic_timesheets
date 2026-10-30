// Режим сетки: «Подробно» (часы, кабинет, время) или «Компактно» (одна строка). Выбор запоминается в браузере.
// Без JavaScript переключателя нет и сетка остаётся подробной.
(function () {
  "use strict";
  var wrap = document.querySelector(".grid-wrap[data-density]");
  var box = document.querySelector("[data-density-switch]");
  if (!wrap || !box) return;
  var KEY = "grid-density";
  var buttons = Array.prototype.slice.call(box.querySelectorAll("[data-density-value]"));

  function apply(mode) {
    wrap.setAttribute("data-density", mode);
    buttons.forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.densityValue === mode ? "true" : "false");
    });
  }

  var saved = null;
  try { saved = window.localStorage.getItem(KEY); } catch (e) { saved = null; }
  apply(saved === "compact" ? "compact" : "detailed");
  box.hidden = false;

  box.addEventListener("click", function (event) {
    var button = event.target.closest("[data-density-value]");
    if (!button) return;
    apply(button.dataset.densityValue);
    try { window.localStorage.setItem(KEY, button.dataset.densityValue); } catch (e) { /* выбор просто не запомнится */ }
  });
})();
