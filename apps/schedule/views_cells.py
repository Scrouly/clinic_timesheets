"""Ввод прямо в ячейку сетки: один адрес, JSON в обе стороны.

Запрос: {"row": id строки графика, "date": "2026-10-01", "raw": "9-15 301", "expected": "..."}.
expected это значение ячейки, которое человек видел, когда начал править; если за это время
ячейку изменили, ответ 409 с текущим значением, и решает человек, а не «побеждает последний».
"""
import json
from datetime import date

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.templatetags.ui_tags import hours

from .cells import CellConflict, CellRejected, apply_cell, cell_payload, issue_state, row_totals
from .models import ScheduleRow
from .views_rows import editable_schedule

RAW_LIMIT = 200


def _bad_request(message):
    return JsonResponse({"ok": False, "error": message}, status=400)


def _read_request(request):
    """(строка, дата, текст, ожидаемое) или текст ошибки."""
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return "Запрос не разобран"
    if not isinstance(data, dict):
        return "Запрос не разобран"
    row_id, raw, expected = data.get("row"), data.get("raw"), data.get("expected")
    if not isinstance(row_id, int) or isinstance(row_id, bool):
        return "Не указана строка"
    if not isinstance(raw, str) or len(raw) > RAW_LIMIT:
        return "Слишком длинный текст ячейки"
    if expected is not None and not isinstance(expected, str):
        return "Неверное ожидаемое значение"
    try:
        day = date.fromisoformat(str(data.get("date")))
    except ValueError:
        return "Неверная дата"
    return row_id, day, raw, expected


def _sign(value):
    return 0 if value is None else (value > 0) - (value < 0)


@require_POST
def cell_apply(request, pk):
    schedule = editable_schedule(request, pk)
    parsed = _read_request(request)
    if isinstance(parsed, str):
        return _bad_request(parsed)
    row_id, day, raw, expected = parsed
    row = get_object_or_404(
        ScheduleRow.objects.select_related("assignment__doctor", "assignment__specialty"),
        pk=row_id,
        schedule=schedule,
    )
    page_path = reverse("schedule_detail", args=[schedule.pk])
    try:
        value = apply_cell(schedule, row, day, raw, expected)
    except CellRejected as error:
        return JsonResponse({"ok": False, "error": str(error)}, status=422)
    except CellConflict as conflict:
        current = cell_payload(schedule, row, day, conflict.current, page_path)
        return JsonResponse({"ok": False, "conflict": True, "current": conflict.current, "cell": current}, status=409)

    cell = cell_payload(schedule, row, day, value, page_path)
    totals = row_totals(schedule, row)
    deviation = None if totals["deviation"] is None else float(totals["deviation"])
    cell["panel_url"] = (
        reverse("shift_update", args=[cell["shift_id"]])
        if cell["shift_id"]
        else f"{reverse('shift_create')}?assignment={row.assignment_id}&date={day.isoformat()}"
    )
    return JsonResponse(
        {
            "ok": True,
            "cell": cell,
            "row": {
                "assignment": row.assignment_id,
                "days": totals["days"],
                "planned": hours(totals["planned"]),
                "norm": hours(totals["norm"]),
                "deviation": hours(totals["deviation"]),
                "deviation_sign": _sign(deviation),
            },
            "issues": issue_state(schedule),
        }
    )
