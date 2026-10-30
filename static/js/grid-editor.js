// Ввод прямо в ячейку сетки графика, как в Excel: выделил ячейку, напечатал «9-15 301», Enter.
// Текст не разбирается в браузере: он уходит на сервер (cellinput.py), обратно приходит
// каноническая запись, итоги строки и состояние проверок. Здесь только выделение, клавиши,
// очередь отправки с повтором и показ результата.
// Включается для устройств с точным указателем; на сенсорных экранах и без JavaScript остаётся форма в панели.
(function () {
  "use strict";
  var wrap = document.querySelector(".grid-wrap[data-editor]");
  if (!wrap) return;
  if (!window.matchMedia || !window.matchMedia("(pointer: fine)").matches) return;

  var table = wrap.querySelector("table.grid");
  var tbody = table.tBodies[0];
  var cfg = { url: wrap.dataset.cellsUrl, csrf: wrap.dataset.csrf, month: wrap.dataset.monthGen || "" };
  var bar = document.querySelector("[data-grid-bar]");
  var barName = bar && bar.querySelector("[data-bar-name]");
  var barInput = bar && bar.querySelector("[data-bar-input]");
  var statusBox = document.querySelector("[data-grid-status]");
  var summary = statusBox && statusBox.querySelector("[data-status-summary]");
  var saveNote = statusBox && statusBox.querySelector("[data-status-save]");
  var conflictBox = statusBox && statusBox.querySelector("[data-conflict]");
  var conflictText = conflictBox && conflictBox.querySelector("[data-conflict-text]");
  var hint = document.querySelector("[data-grid-hint]");
  var help = document.querySelector("[data-grid-help]");
  var issuesBox = document.querySelector("[data-issues]");
  var storeKey = "grid-cell:" + location.pathname;

  var FLAG = '<svg class="icon icon--small cell__flag" aria-hidden="true"><use href="#i-alert"/></svg>' +
    '<span class="sr-only">Накладка или ошибка</span>';

  var active = null;      // выделенная ячейка
  var editing = null;     // {cell, typed, source: "cell" | "bar", value}
  var queue = [];         // очередь отправки; первый элемент отправляется сейчас
  var sending = false;
  var retries = 0;
  var retryTimer = null;
  var conflicts = [];

  // ---------- вспомогательное

  function rowsList() { return Array.prototype.slice.call(tbody.querySelectorAll("tr[data-assignment]")); }
  function rowCells(row) { return Array.prototype.slice.call(row.querySelectorAll("td.cell")); }
  function rowOf(cell) { return cell.parentNode; }
  function isCell(node) { return !!node && node.nodeType === 1 && node.tagName === "TD" && node.classList.contains("cell"); }

  function cellAt(rowIndex, colIndex) {
    var rows = rowsList();
    if (!rows.length) return null;
    var row = rows[Math.max(0, Math.min(rows.length - 1, rowIndex))];
    var cells = rowCells(row);
    return cells[Math.max(0, Math.min(cells.length - 1, colIndex))] || null;
  }
  function position(cell) {
    var row = rowOf(cell);
    return { r: rowsList().indexOf(row), c: rowCells(row).indexOf(cell) };
  }
  function shortName(cell) {
    var name = rowOf(cell).querySelector(".grid__name");
    return name ? name.textContent.trim() : "";
  }
  function dayName(cell) { return cell.dataset.day + " " + cfg.month; }

  function cellLabel(cell) {
    var value = cell.dataset.value || "пусто";
    var label = shortName(cell) + ", " + dayName(cell) + ", " + value;
    if (cell.classList.contains("cell--error")) label += ", накладка или ошибка";
    if (cell.classList.contains("cell--unsaved")) label += ", не сохранено";
    return label;
  }
  function refreshLabel(cell) { cell.setAttribute("aria-label", cellLabel(cell)); }

  // блоки смен ячейки (сверху вниз: часы, кабинет, время) в виде простых объектов
  function itemsOf(container) {
    return Array.prototype.map.call(container.querySelectorAll(".cell__item"), function (item) {
      var time = item.querySelector(".cell__time");
      var cab = item.querySelector(".cell__cab");
      var hours = item.querySelector(".cell__hours");
      return {
        label: time ? time.textContent.trim() : "",
        cabinet: cab ? cab.textContent.trim() : "",
        hours: hours ? hours.textContent.trim() : "",
        kind: item.classList.contains("cell__item--kind"),
        pending: item.classList.contains("cell__item--pending")
      };
    });
  }
  function readItems(cell) { return itemsOf(cell); }

  function clearItems(cell) {
    Array.prototype.forEach.call(cell.querySelectorAll(".cell__item"), function (node) { node.remove(); });
  }

  function line(className, text) {
    var node = document.createElement("span");
    node.className = className;
    node.textContent = text;  // textContent: ввод и названия кабинетов не становятся разметкой
    return node;
  }

  // блоки смен рисуются из объектов: так показывается введённый, но ещё не сохранённый текст и возврат при отказе
  function renderItems(cell, items) {
    clearItems(cell);
    var first = cell.firstChild;
    items.forEach(function (item) {
      var box = document.createElement("span");
      box.className = "cell__item" + (item.kind ? " cell__item--kind" : "") + (item.pending ? " cell__item--pending" : "");
      if (item.hours) box.appendChild(line("cell__hours", item.hours));
      if (item.cabinet) box.appendChild(line("cell__cab", item.cabinet));
      box.appendChild(line("cell__time", item.label));
      cell.insertBefore(box, first);
    });
  }

  // содержимое ячейки, собранное сервером (экранировано Django): подставляется как есть, чтобы
  // до и после сохранения ячейка выглядела одинаково
  function htmlHolder(html) {
    var box = document.createElement("div");
    box.innerHTML = html;  // разметка от сервера, только для чтения значений
    return box;
  }

  function itemsFromPayload(payload) {
    return typeof payload.html === "string" ? itemsOf(htmlHolder(payload.html)) : payload.items;
  }

  function showHtml(cell, html) {
    clearItems(cell);
    if (!html || !html.trim()) return;
    var holder = document.createElement("template");
    holder.innerHTML = html;
    Array.prototype.forEach.call(holder.content.querySelectorAll("a.cell__link"), function (link) {
      link.setAttribute("tabindex", "-1");
    });
    cell.insertBefore(holder.content, cell.firstChild);
  }

  function setKind(cell, kind) {
    cell.classList.remove("cell--shift", "cell--absence", "cell--off");
    cell.classList.add("cell--" + kind);
  }

  function formatTime(date) {
    return ("0" + date.getHours()).slice(-2) + ":" + ("0" + date.getMinutes()).slice(-2);
  }
  function saveStatus(text) { if (saveNote) saveNote.textContent = text; }

  // ---------- выделение и обновление строк состояния

  function describeSelection(cell) {
    var row = rowOf(cell);
    var planned = row.querySelector("[data-sum=planned]");
    var norm = row.querySelector("[data-sum=norm]");
    var text = "Выбрано: " + shortName(cell) + ", " + dayName(cell);
    if (planned && norm) text += " · Часов в строке " + planned.textContent.trim() + " из нормы " + norm.textContent.trim();
    return text;
  }

  function updateBars() {
    if (!active) return;
    if (summary) summary.textContent = describeSelection(active);
    if (barName) barName.textContent = shortName(active) + ", " + dayName(active);
    if (barInput && !(editing && editing.source === "bar")) {
      barInput.disabled = false;
      if (!editing) barInput.value = active.dataset.value || "";
    }
  }

  function setActive(cell) {
    if (active && active !== cell) {
      active.setAttribute("tabindex", "-1");
      active.classList.remove("is-active");
    }
    active = cell;
    cell.setAttribute("tabindex", "0");
    cell.classList.add("is-active");
    clearHint(cell);
    updateBars();
    try { sessionStorage.setItem(storeKey, rowOf(cell).dataset.row + "|" + cell.dataset.date); } catch (e) { /* без хранилища не запоминаем */ }
  }

  function select(cell, focus) {
    if (!cell) return;
    setActive(cell);
    if (focus !== false) {
      cell.focus({ preventScroll: true });
      if (cell.scrollIntoView) cell.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  function move(rowDelta, colDelta) {
    if (!active) return;
    var at = position(active);
    var rows = rowsList();
    var r = at.r + rowDelta;
    var c = at.c + colDelta;
    var width = rowCells(rowOf(active)).length;
    if (colDelta > 0 && c >= width) { r += 1; c = 0; }
    if (colDelta < 0 && c < 0) { r -= 1; c = width - 1; }
    if (r < 0 || r >= rows.length) return false;
    select(cellAt(r, c));
    return true;
  }

  // ---------- подсказка под ячейкой

  function clearHint(cell) {
    var node = cell.querySelector(".cell__hint");
    if (node) node.remove();
  }
  function showHint(cell, message) {
    clearHint(cell);
    var node = document.createElement("span");
    node.className = "cell__hint";
    node.textContent = message;
    cell.appendChild(node);
    window.setTimeout(function () { if (node.parentNode) node.remove(); }, 9000);
  }

  // ---------- редактирование

  var editor = document.createElement("input");
  editor.type = "text";
  editor.className = "cell__editor";
  editor.autocomplete = "off";
  editor.spellcheck = false;
  editor.setAttribute("enterkeyhint", "done");

  function beginEdit(cell, initial, typed, source) {
    if (editing) finishEdit(true, false);
    select(cell, source !== "bar");
    clearHint(cell);
    editing = { cell: cell, typed: !!typed, source: source || "cell", value: initial };
    cell.classList.add("is-editing");
    if (editing.source === "cell") {
      editor.setAttribute("aria-label", "Ввод: " + shortName(cell) + ", " + dayName(cell));
      editor.value = initial;
      cell.appendChild(editor);
      editor.focus();
      editor.setSelectionRange(initial.length, initial.length);
    }
    if (barInput) { barInput.disabled = false; barInput.value = initial; }
  }

  // commit: сохранить введённое; moveBy: куда перейти после
  function finishEdit(commit, refocus) {
    if (!editing) return;
    var state = editing;
    var cell = state.cell;
    editing = null;
    cell.classList.remove("is-editing");
    if (editor.parentNode === cell) cell.removeChild(editor);
    if (refocus !== false) cell.focus({ preventScroll: true });
    if (barInput) barInput.value = cell.dataset.value || "";
    if (commit) submit(cell, state.value);
  }

  editor.addEventListener("input", function () {
    if (!editing) return;
    editing.value = editor.value;
    if (barInput) barInput.value = editor.value;
  });
  editor.addEventListener("blur", function (event) {
    if (!editing || editing.source !== "cell") return;
    if (event.relatedTarget === barInput) { editing.source = "bar"; return; }
    finishEdit(true, false);
  });

  function editorKey(event) {
    var key = event.key;
    if (key === "Enter") { event.preventDefault(); finishEdit(true); move(event.shiftKey ? -1 : 1, 0); return; }
    if (key === "Tab") { event.preventDefault(); finishEdit(true); move(0, event.shiftKey ? -1 : 1); return; }
    if (key === "Escape") { event.preventDefault(); finishEdit(false); return; }
    // начатый печатью ввод ведёт себя как в Excel: стрелки сохраняют и переходят
    if (editing && editing.typed && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
      var deltas = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
      if (deltas[key]) {
        event.preventDefault();
        finishEdit(true);
        move(deltas[key][0], deltas[key][1]);
      }
    }
  }

  // ---------- клавиши на выделенной ячейке

  function cellKey(event, cell) {
    var key = event.key;
    var ctrl = event.ctrlKey || event.metaKey;
    if (ctrl && (key === "Home" || key === "End")) {
      event.preventDefault();
      var rows = rowsList();
      if (key === "Home") select(cellAt(0, 0)); else select(cellAt(rows.length - 1, rowCells(rows[rows.length - 1]).length - 1));
      return;
    }
    if (ctrl || event.altKey) return;  // Ctrl+C, Ctrl+V и прочее обрабатывает браузер

    if (key === "ArrowUp") { event.preventDefault(); move(-1, 0); }
    else if (key === "ArrowDown") { event.preventDefault(); move(1, 0); }
    else if (key === "ArrowLeft") { event.preventDefault(); move(0, -1); }
    else if (key === "ArrowRight") { event.preventDefault(); move(0, 1); }
    else if (key === "Home") { event.preventDefault(); select(cellAt(position(cell).r, 0)); }
    else if (key === "End") { event.preventDefault(); select(cellAt(position(cell).r, rowCells(rowOf(cell)).length - 1)); }
    else if (key === "Tab") { if (move(0, event.shiftKey ? -1 : 1)) event.preventDefault(); }
    else if (key === "F2" && event.shiftKey) { event.preventDefault(); openPanel(cell); }
    else if (key === "F2" || key === "Enter") {
      event.preventDefault();
      if (key === "Enter" && event.shiftKey) { move(-1, 0); return; }
      beginEdit(cell, cell.dataset.value || "", false);
    }
    else if (key === "Delete" || key === "Backspace") { event.preventDefault(); submit(cell, ""); }
    else if (key === "?") { event.preventDefault(); openHelp(); }
    else if (key.length === 1) {  // любой символ: ввод вместо текущего значения
      event.preventDefault();
      beginEdit(cell, key, true);
    }
  }

  table.addEventListener("keydown", function (event) {
    var target = event.target;
    if (target === editor) { editorKey(event); return; }
    if (!isCell(target)) return;  // меню строки, кнопки «＋» и поле поиска врача живут по-своему
    cellKey(event, target);
  });
  table.addEventListener("focusin", function (event) {
    if (isCell(event.target) && event.target !== active) setActive(event.target);
  });
  table.addEventListener("click", function (event) {
    var cell = event.target.closest && event.target.closest("td.cell");
    if (!cell || event.target === editor) return;
    if (editing && editing.cell !== cell) finishEdit(true, false);
    select(cell);
  });
  table.addEventListener("dblclick", function (event) {
    var cell = event.target.closest && event.target.closest("td.cell");
    if (cell && event.target !== editor) beginEdit(cell, cell.dataset.value || "", false);
  });

  // ---------- строка ввода над сеткой

  if (barInput) {
    barInput.addEventListener("focus", function () {
      if (active && !editing) beginEdit(active, active.dataset.value || "", false, "bar");
    });
    barInput.addEventListener("input", function () {
      if (!editing) return;
      editing.value = barInput.value;
      if (editor.parentNode) editor.value = barInput.value;
    });
    barInput.addEventListener("keydown", function (event) {
      if (!editing) return;
      if (event.key === "Enter") { event.preventDefault(); finishEdit(true); move(1, 0); }
      else if (event.key === "Escape") { event.preventDefault(); finishEdit(false); }
    });
    barInput.addEventListener("blur", function (event) {
      if (editing && editing.source === "bar" && event.relatedTarget !== editor) finishEdit(true, false);
    });
  }

  // ---------- отправка на сервер

  function submit(cell, raw) {
    raw = raw.replace(/^\s+|\s+$/g, "");
    var known = cell.dataset.value || "";
    var pending = queue.some(function (item) { return item.cell === cell; });
    if (raw === known && !pending) return;  // ничего не изменилось
    cell.classList.add("cell--pending");
    cell.classList.remove("cell--unsaved");
    renderItems(cell, raw ? [{ label: raw, cabinet: "", hours: "", kind: true, pending: true }] : []);
    queue.push({ cell: cell, raw: raw });
    pump();
  }

  function request(item) {
    return fetch(cfg.url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json", Accept: "application/json",
        "X-CSRFToken": cfg.csrf, "X-Requested-With": "fetch"
      },
      body: JSON.stringify({
        row: parseInt(rowOf(item.cell).dataset.row, 10),
        date: item.cell.dataset.date,
        raw: item.raw,
        expected: item.expected !== undefined ? item.expected : (item.cell.dataset.value || "")
      })
    }).then(function (response) {
      return response.json().then(function (data) { return { status: response.status, data: data }; },
        function () { return { status: response.status, data: {} }; });
    });
  }

  function pump() {
    if (sending || !queue.length) return;
    window.clearTimeout(retryTimer);
    var item = queue[0];
    sending = true;
    saveStatus("Сохраняю…");
    request(item).then(function (result) { sending = false; handle(item, result); },
      function () { sending = false; failed(item); });
  }

  function revert(cell) {
    renderItems(cell, cell._items || []);
    cell.classList.remove("cell--pending", "cell--unsaved");
    refreshLabel(cell);
  }

  function handle(item, result) {
    var status = result.status;
    var data = result.data || {};
    var cell = item.cell;
    if (status === 200 && data.ok) {
      queue.shift();
      retries = 0;
      applySaved(cell, data);
      saveStatus("Сохранено " + formatTime(new Date()));
      pump();
    } else if (status === 422) {
      queue.shift();
      revert(cell);
      showHint(cell, data.error || "Не понял ввод");
      saveStatus(data.error || "Не понял ввод");
      pump();
    } else if (status === 409) {
      queue.shift();
      applyCell(cell, data.cell);
      conflicts.push({ cell: cell, raw: item.raw, current: data.current, payload: data.cell });
      cell.classList.add("cell--conflict");
      showConflict();
      pump();
    } else if (status >= 500 || status === 0) {
      failed(item);
    } else {
      queue.shift();
      revert(cell);
      var message = status === 403 ? "Нет права менять этот график или сессия истекла. Обновите страницу."
        : "Не получилось сохранить. Обновите страницу и повторите.";
      showHint(cell, message);
      saveStatus(message);
      pump();
    }
  }

  function failed(item) {
    retries += 1;
    item.cell.classList.add("cell--unsaved");
    refreshLabel(item.cell);
    saveStatus("Не сохранено, повторяю (" + retries + ")…");
    var delay = Math.min(2000 * Math.pow(2, retries - 1), 15000);
    retryTimer = window.setTimeout(pump, delay);
  }

  window.addEventListener("online", function () { if (queue.length && !sending) { window.clearTimeout(retryTimer); pump(); } });
  window.addEventListener("beforeunload", function (event) {
    if (queue.length || sending || conflicts.length) { event.preventDefault(); event.returnValue = ""; }
  });

  // ---------- показ результата

  function applyCell(cell, payload) {
    if (typeof payload.html === "string") {
      showHtml(cell, payload.html);
      cell._items = readItems(cell);
    } else {
      renderItems(cell, payload.items);
      cell._items = payload.items;
    }
    setKind(cell, payload.kind);
    cell.dataset.value = payload.value;
    cell.classList.remove("cell--pending", "cell--unsaved");
    if (payload.panel_url) cell.dataset.panelUrl = payload.panel_url;
    refreshLabel(cell);
  }

  function applySaved(cell, data) {
    // если в эту же ячейку уже ввели новое значение, на экране остаётся оно, пока не придёт его ответ
    var waiting = queue.some(function (item) { return item.cell === cell; });
    if (waiting) {
      cell.dataset.value = data.cell.value;
      cell._items = itemsFromPayload(data.cell);
    } else {
      applyCell(cell, data.cell);
    }
    updateTotals(data.row);
    applyIssues(data.issues);
    if (active === cell) updateBars();
  }

  function updateTotals(row) {
    var tr = tbody.querySelector('tr[data-assignment="' + row.assignment + '"]');
    if (!tr) return;
    var set = function (name, text) { var td = tr.querySelector("[data-sum=" + name + "]"); if (td) td.textContent = text; };
    set("days", String(row.days));
    set("planned", row.planned);
    set("norm", row.norm);
    set("deviation", row.deviation);
    var dev = tr.querySelector("[data-sum=deviation]");
    if (dev) {
      dev.classList.toggle("is-short", row.deviation_sign < 0);
      dev.classList.toggle("is-over", row.deviation_sign > 0);
    }
  }

  function applyIssues(issues) {
    var bad = {};
    issues.cells.forEach(function (item) { bad[item.assignment + "|" + item.date] = true; });
    rowsList().forEach(function (row) {
      rowCells(row).forEach(function (cell) {
        var has = !!bad[row.dataset.assignment + "|" + cell.dataset.date];
        var was = cell.classList.contains("cell--error");
        if (has === was) return;
        cell.classList.toggle("cell--error", has);
        Array.prototype.forEach.call(cell.querySelectorAll(".cell__flag, .cell > .sr-only"), function (node) { node.remove(); });
        if (has) cell.insertAdjacentHTML("afterbegin", FLAG);
        refreshLabel(cell);
      });
    });
    if (!issuesBox) return;
    var list = issuesBox.querySelector("[data-issues-list]");
    var count = issuesBox.querySelector("[data-issues-count]");
    while (list.firstChild) list.removeChild(list.firstChild);
    issues.messages.forEach(function (message) {
      var li = document.createElement("li");
      li.textContent = message;
      list.appendChild(li);
    });
    if (count) count.textContent = String(issues.messages.length);
    issuesBox.hidden = issues.messages.length === 0;
  }

  // ---------- конфликт: решает человек

  function showConflict() {
    if (!conflicts.length) { conflictBox.hidden = true; return; }
    var first = conflicts[0];
    var text = "Эту ячейку уже изменили: " + shortName(first.cell) + ", " + dayName(first.cell) + ". Сейчас там «" +
      (first.current || "пусто") + "», вы ввели «" + (first.raw || "пусто") + "».";
    if (conflicts.length > 1) text += " Ещё конфликтов: " + (conflicts.length - 1) + ".";
    conflictText.textContent = text;
    conflictBox.hidden = false;
    select(first.cell, false);
  }

  function resolve(keepMine) {
    var first = conflicts.shift();
    if (!first) return;
    var cell = first.cell;
    cell.classList.remove("cell--conflict");
    if (keepMine) {
      cell.dataset.value = first.current;  // теперь ждём именно это значение
      cell._items = itemsFromPayload(first.payload);
      submit(cell, first.raw);
    }
    showConflict();
    cell.focus({ preventScroll: true });
  }
  if (conflictBox) {
    conflictBox.querySelector("[data-conflict-mine]").addEventListener("click", function () { resolve(true); });
    conflictBox.querySelector("[data-conflict-theirs]").addEventListener("click", function () { resolve(false); });
  }

  // ---------- форма смены и справка

  function panelUrl(cell) {
    var link = cell.querySelector("a[data-panel-link]");
    var url = cell.dataset.panelUrl || (link ? link.getAttribute("href") : "");
    if (!url) return "";
    if (/[?&]next=/.test(url)) return url;
    return url + (url.indexOf("?") === -1 ? "?" : "&") + "next=" + encodeURIComponent(location.pathname + location.search);
  }
  function openPanel(cell) {
    var url = panelUrl(cell);
    if (!url) return;
    if (window.ClinicGrid && window.ClinicGrid.openPanel) window.ClinicGrid.openPanel(url);
    else window.location.href = url;
  }
  function openHelp() {
    if (help && typeof help.showModal === "function" && !help.open) help.showModal();
  }

  // ---------- запуск

  table.classList.add("grid--editor");
  table.setAttribute("role", "grid");
  table.setAttribute("aria-label", "График: стрелки перемещают по ячейкам, печатайте время, например 9-15 301");
  wrap.classList.add("is-editor");
  if (bar) bar.hidden = false;
  if (statusBox) statusBox.hidden = false;
  if (hint) hint.hidden = false;

  Array.prototype.forEach.call(table.querySelectorAll("a.cell__link, a.cell__add"), function (link) {
    link.setAttribute("tabindex", "-1");
  });
  rowsList().forEach(function (row) {
    rowCells(row).forEach(function (cell) {
      cell.setAttribute("tabindex", "-1");
      cell._items = readItems(cell);
      refreshLabel(cell);
    });
  });

  var saved = null;
  try { saved = sessionStorage.getItem(storeKey); } catch (e) { saved = null; }
  var start = null;
  if (saved) {
    var parts = saved.split("|");
    var row = document.getElementById("row-" + parts[0]);
    start = row && row.querySelector('td.cell[data-date="' + parts[1] + '"]');
  }
  start = start || cellAt(0, 0);
  if (start) { start.setAttribute("tabindex", "0"); setActive(start); }

  // для grid-rows.js: после добавления строки курсор встаёт в её первую ячейку
  window.ClinicGrid = window.ClinicGrid || {};
  window.ClinicGrid.focusFirstCell = function (row) {
    var cells = row ? rowCells(row) : [];
    if (!cells.length) return false;
    select(cells[0]);
    return true;
  };
})();
