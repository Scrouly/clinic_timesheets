/* Небольшие помощники интерфейса. Без библиотек и без запросов в интернет. */
(function () {
  "use strict";
  var body = document.body;

  // Меню на узких экранах
  var toggle = document.querySelector("[data-nav-toggle]");
  var scrim = document.querySelector("[data-nav-scrim]");
  function setNav(open) {
    body.classList.toggle("nav-open", open);
    if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (toggle) toggle.addEventListener("click", function () { setNav(!body.classList.contains("nav-open")); });
  if (scrim) scrim.addEventListener("click", function () { setNav(false); });

  // Меню пользователя: закрывается кликом снаружи и клавишей Esc
  var menu = document.querySelector(".usermenu");
  document.addEventListener("click", function (event) {
    if (menu && menu.open && !menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (menu && menu.open) { menu.open = false; menu.querySelector("summary").focus(); }
    setNav(false);
  });

  // Закрытие сообщений; успешные скрываются сами через 8 секунд
  document.querySelectorAll("[data-dismiss]").forEach(function (button) {
    button.addEventListener("click", function () { button.closest(".msg").remove(); });
  });
  document.querySelectorAll(".msg--success").forEach(function (message) {
    setTimeout(function () { message.remove(); }, 8000);
  });

  // Подтверждение опасных действий: <button data-confirm="Удалить график?">
  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-confirm]");
    if (target && !window.confirm(target.getAttribute("data-confirm"))) event.preventDefault();
  });
})();
