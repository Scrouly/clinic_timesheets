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


  // Боковая панель правки смены. Без JavaScript ссылки ведут на обычную страницу формы.
  var panel = document.querySelector("[data-panel]");
  var scrollKey = "grid-scroll:" + location.pathname + location.search;

  function saveScroll() {
    try {
      var wrap = document.querySelector(".grid-wrap");
      sessionStorage.setItem(scrollKey, JSON.stringify({
        x: window.scrollX, y: window.scrollY,
        gx: wrap ? wrap.scrollLeft : 0, gy: wrap ? wrap.scrollTop : 0
      }));
    } catch (e) { /* хранилище недоступно: просто не запоминаем положение */ }
  }
  function restoreScroll() {
    try {
      var raw = sessionStorage.getItem(scrollKey);
      if (!raw) return;
      sessionStorage.removeItem(scrollKey);
      var pos = JSON.parse(raw);
      var wrap = document.querySelector(".grid-wrap");
      window.scrollTo(pos.x, pos.y);
      if (wrap) { wrap.scrollLeft = pos.gx; wrap.scrollTop = pos.gy; }
    } catch (e) { /* ничего страшного */ }
  }
  restoreScroll();
  window.ClinicGrid = { saveScroll: saveScroll };  // для grid-rows.js: запомнить прокрутку перед перезагрузкой

  if (panel && typeof panel.showModal === "function") {
    var panelBody = panel.querySelector("[data-panel-body]");
    var FETCH = { "X-Requested-With": "fetch" };

    var showForm = function (html) {
      panelBody.innerHTML = html;
      var target = panelBody.querySelector(".field--invalid input, .field--invalid select")
        || panelBody.querySelector("input:not([type=hidden]), select, textarea");
      if (target) target.focus();
    };
    var openPanel = function (url) {
      panelBody.innerHTML = '<p class="side-panel__loading" role="status">Загрузка…</p>';
      if (!panel.open) panel.showModal();
      fetch(url, { headers: FETCH, credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error(response.status); return response.text(); })
        .then(showForm)
        .catch(function () { window.location.href = url; });
    };

    document.addEventListener("click", function (event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      var link = event.target.closest("[data-panel-link]");
      if (link) { event.preventDefault(); openPanel(link.href); return; }
      if (event.target.closest("[data-panel-close]")) panel.close();
      else if (event.target === panel) panel.close();  // щелчок по затемнению
    });

    panel.addEventListener("submit", function (event) {
      var form = event.target.closest("[data-shift-form], [data-panel-form]");
      if (!form) return;
      event.preventDefault();
      fetch(form.action, { method: "POST", body: new FormData(form), headers: FETCH, credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) throw new Error(response.status);
          var type = response.headers.get("Content-Type") || "";
          if (type.indexOf("application/json") === 0) {
            saveScroll();
            window.location.reload();
            return null;
          }
          return response.text().then(showForm);
        })
        .catch(function () { window.location.reload(); });
    });
  }
  // Подтверждение опасных действий: <button data-confirm="Удалить график?">
  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-confirm]");
    if (target && !window.confirm(target.getAttribute("data-confirm"))) event.preventDefault();
  });
})();
