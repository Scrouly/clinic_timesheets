// Состав строк графика: «＋» между строками, строка-заготовка с поиском врача и меню строки.
// Страница после действия перезагружается (так же, как после правки смены), курсор встаёт в новую строку.
(function () {
  "use strict";
  var wrap = document.querySelector(".grid-wrap[data-rows]");
  if (!wrap) return;

  var config = { search: wrap.dataset.searchUrl, create: wrap.dataset.createUrl, csrf: wrap.dataset.csrf };
  var table = wrap.querySelector("table.grid");
  var tbody = table.tBodies[0];
  var template = document.getElementById("row-picker-template");
  var menu = document.getElementById("row-menu");
  var focusKey = "grid-focus:" + location.pathname;
  var FETCH = { "X-Requested-With": "fetch" };

  function dataRows() {
    return Array.prototype.slice.call(tbody.querySelectorAll("tr[id^='row-']"));
  }

  function afterReload(rowId) {
    if (window.ClinicGrid) window.ClinicGrid.saveScroll();
    try { sessionStorage.setItem(focusKey, rowId ? "row-" + rowId : ""); } catch (e) { /* без хранилища просто не ставим курсор */ }
    window.location.reload();
  }

  // ---- после перезагрузки: курсор в первую ячейку новой или перемещённой строки
  (function restoreFocus() {
    var id;
    try { id = sessionStorage.getItem(focusKey); sessionStorage.removeItem(focusKey); } catch (e) { return; }
    var row = id && document.getElementById(id);
    if (!row) return;
    if (window.ClinicGrid && window.ClinicGrid.focusFirstCell && window.ClinicGrid.focusFirstCell(row)) {
      row.classList.add("row--new");
      window.setTimeout(function () { row.classList.remove("row--new"); }, 3000);
      return;
    }
    var target = row.querySelector(".cell__add, .cell__link") || row.querySelector("button");
    if (target) target.focus();
    row.classList.add("row--new");
    window.setTimeout(function () { row.classList.remove("row--new"); }, 3000);
  })();

  // ---- меню строки
  var menuButton = null;
  var supportsPopover = menu && typeof menu.showPopover === "function";

  function menuItems() {
    return Array.prototype.slice.call(menu.querySelectorAll("[role=menuitem]:not([hidden])"));
  }

  function openMenu(button) {
    if (!supportsPopover) { window.location.href = button.dataset.editUrl; return; }
    menuButton = button;
    menu.querySelector("[data-menu=edit]").setAttribute("href", button.dataset.editUrl);
    menu.querySelector("[data-menu=remove]").setAttribute("href", button.dataset.removeUrl);
    menu.querySelector("[data-menu=up]").hidden = !!button.dataset.first;
    menu.querySelector("[data-menu=down]").hidden = !!button.dataset.last;
    var box = button.getBoundingClientRect();
    menu.style.top = Math.min(box.bottom + 4, window.innerHeight - 220) + "px";
    menu.style.left = Math.max(8, Math.min(box.left, window.innerWidth - 260)) + "px";
    menu.showPopover();
    button.setAttribute("aria-expanded", "true");
    menuItems()[0].focus();
  }

  function closeMenu() {
    if (supportsPopover && menu.matches(":popover-open")) menu.hidePopover();
  }

  if (supportsPopover) {
    menu.addEventListener("toggle", function (event) {
      if (event.newState === "closed" && menuButton) {
        menuButton.setAttribute("aria-expanded", "false");
        if (document.activeElement === document.body || menu.contains(document.activeElement)) menuButton.focus();
      }
    });
    menu.addEventListener("keydown", function (event) {
      var items = menuItems();
      var index = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown") { event.preventDefault(); items[(index + 1) % items.length].focus(); }
      else if (event.key === "ArrowUp") { event.preventDefault(); items[(index - 1 + items.length) % items.length].focus(); }
      else if (event.key === "Home") { event.preventDefault(); items[0].focus(); }
      else if (event.key === "End") { event.preventDefault(); items[items.length - 1].focus(); }
      else if (event.key === "Tab") { closeMenu(); }
    });
    menu.addEventListener("click", function (event) {
      var item = event.target.closest("[data-menu]");
      if (!item) return;
      var button = menuButton;
      var action = item.dataset.menu;
      closeMenu();
      if (action === "add") openPicker(parseInt(button.dataset.position, 10), button);
      else if (action === "up" || action === "down") moveRow(button, action);
      // «edit» и «remove» это ссылки data-panel-link: их открывает боковая панель из app.js
    });
  }

  function moveRow(button, direction) {
    var row = button.closest("tr");
    var body = new FormData();
    body.append("direction", direction);
    body.append("csrfmiddlewaretoken", config.csrf);
    fetch(button.dataset.moveUrl, { method: "POST", body: body, headers: Object.assign({ Accept: "application/json" }, FETCH), credentials: "same-origin" })
      .then(function (response) { if (!response.ok) throw new Error(response.status); afterReload(row.id.replace("row-", "")); })
      .catch(function () { window.alert("Не получилось переместить строку. Обновите страницу и повторите."); });
  }

  // ---- строка-заготовка с поиском врача
  var picker = null;

  function closePicker(returnFocus) {
    if (!picker) return;
    var trigger = picker.trigger;
    picker.row.remove();
    picker = null;
    if (returnFocus && trigger && document.contains(trigger)) trigger.focus();
  }

  function openPicker(position, trigger) {
    closePicker(false);
    var row = template.content.firstElementChild.cloneNode(true);
    var rows = dataRows();
    var before = position < rows.length ? rows[position] : tbody.querySelector(".grid__add-row");
    tbody.insertBefore(row, before);

    var form = row.querySelector("form");
    var input = row.querySelector("[data-picker-input]");
    var list = row.querySelector("[data-picker-list]");
    var specialty = row.querySelector("[data-picker-specialty]");
    var rate = row.querySelector("[data-picker-rate]");
    var status = row.querySelector("[data-picker-status]");
    var submit = row.querySelector("button[type=submit]");
    input.id = "row-picker-doctor"; list.id = "row-picker-list"; specialty.id = "row-picker-specialty"; rate.id = "row-picker-rate";
    row.querySelector("[data-picker-doctor-label]").htmlFor = input.id;
    row.querySelector("[data-picker-specialty-label]").htmlFor = specialty.id;
    row.querySelector("[data-picker-rate-label]").htmlFor = rate.id;
    input.setAttribute("aria-controls", list.id);
    picker = { row: row, trigger: trigger };

    var results = [];
    var active = -1;
    var chosen = null;
    var timer = null;
    var requestNumber = 0;

    function say(text) { status.textContent = text || ""; }

    function showList(items) {
      results = items;
      active = items.length ? 0 : -1;
      list.innerHTML = "";
      items.forEach(function (doctor, index) {
        var li = document.createElement("li");
        li.id = "row-picker-option-" + index;
        li.setAttribute("role", "option");
        li.className = "row-picker__option";
        li.setAttribute("aria-selected", index === active ? "true" : "false");
        var main = document.createElement("span");
        main.textContent = doctor.name;
        var meta = document.createElement("span");
        meta.className = "row-picker__meta";
        meta.textContent = doctor.tab_number ? "таб. " + doctor.tab_number : "";
        li.appendChild(main); li.appendChild(meta);
        li.addEventListener("mousedown", function (event) { event.preventDefault(); choose(index); });
        list.appendChild(li);
      });
      list.hidden = !items.length;
      input.setAttribute("aria-expanded", items.length ? "true" : "false");
      if (items.length) input.setAttribute("aria-activedescendant", "row-picker-option-" + active);
      else input.removeAttribute("aria-activedescendant");
    }

    function move(delta) {
      if (!results.length) return;
      active = (active + delta + results.length) % results.length;
      Array.prototype.forEach.call(list.children, function (li, index) {
        li.setAttribute("aria-selected", index === active ? "true" : "false");
      });
      input.setAttribute("aria-activedescendant", "row-picker-option-" + active);
      list.children[active].scrollIntoView({ block: "nearest" });
    }

    function search() {
      var mine = ++requestNumber;  // ответы приходят не по порядку: берём только последний
      fetch(config.search + "?q=" + encodeURIComponent(input.value.trim()), { headers: FETCH, credentials: "same-origin" })
        .then(function (response) { if (!response.ok) throw new Error(response.status); return response.json(); })
        .then(function (data) {
          if (mine !== requestNumber || chosen) return;
          showList(data.results);
          say(data.results.length ? data.results.length + " найдено. Стрелки выбирают, Enter подтверждает." : "Никого не нашли. Нужного человека заводит кадровик.");
        })
        .catch(function () { say("Не получилось загрузить список. Проверьте соединение."); });
    }

    function choose(index) {
      var doctor = results[index];
      if (!doctor) return;
      chosen = doctor;
      input.value = doctor.name + (doctor.tab_number ? " · таб. " + doctor.tab_number : "");
      showList([]);
      specialty.value = doctor.specialty ? String(doctor.specialty) : "";
      rate.value = doctor.rate;
      var present = doctor.in_schedule.indexOf(doctor.specialty) !== -1;
      say(present ? "Этот врач с такой профессией уже есть в графике. Выберите другую профессию." : "");
      (specialty.value && !present ? submit : specialty).focus();
    }

    input.addEventListener("input", function () {
      chosen = null;
      window.clearTimeout(timer);
      timer = window.setTimeout(search, 150);
    });
    input.addEventListener("focus", function () { if (!chosen && !results.length) search(); });
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); if (list.hidden) search(); else move(1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
      else if (event.key === "Enter") {
        if (!list.hidden && active >= 0) { event.preventDefault(); choose(active); }
        else if (chosen) { event.preventDefault(); form.requestSubmit(); }
      } else if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation();
        if (!list.hidden) showList([]); else closePicker(true);
      }
    });
    input.addEventListener("blur", function () { window.setTimeout(function () { if (picker && picker.row === row) showList([]); }, 150); });
    row.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && event.target !== input) { event.preventDefault(); closePicker(true); }
    });
    row.querySelector("[data-picker-cancel]").addEventListener("click", function () { closePicker(true); });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!chosen) { say("Выберите врача из списка."); input.focus(); return; }
      if (!specialty.value) { say("Выберите профессию."); specialty.focus(); return; }
      var body = new FormData();
      body.append("doctor", chosen.id);
      body.append("specialty", specialty.value);
      body.append("rate", rate.value);
      body.append("position", String(position));
      body.append("csrfmiddlewaretoken", config.csrf);
      submit.disabled = true;
      fetch(config.create, { method: "POST", body: body, headers: Object.assign({ Accept: "application/json" }, FETCH), credentials: "same-origin" })
        .then(function (response) { return response.json().then(function (data) { return { ok: response.ok, data: data }; }); })
        .then(function (result) {
          if (result.ok && result.data.ok) { afterReload(result.data.row); return; }
          var errors = result.data.errors || {};
          var messages = [];
          Object.keys(errors).forEach(function (key) { messages = messages.concat(errors[key]); });
          say(messages.join(" ") || "Не получилось добавить врача.");
          submit.disabled = false;
        })
        .catch(function () { say("Не получилось добавить врача. Проверьте соединение и повторите."); submit.disabled = false; });
    });

    row.scrollIntoView({ block: "nearest" });
    input.focus();
  }

  // ---- кнопки
  document.addEventListener("click", function (event) {
    var add = event.target.closest("[data-row-add]");
    if (add) { event.preventDefault(); openPicker(parseInt(add.dataset.position, 10), add); return; }
    var toggle = event.target.closest("[data-row-menu]");
    if (toggle) { event.preventDefault(); openMenu(toggle); }
  });
})();
