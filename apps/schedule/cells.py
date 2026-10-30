"""Применение текста ячейки к сменам и ответ для сетки.

Ячейка это все записи Shift одной строки графика за один день. Текст из ячейки разбирается
в cellinput.py, здесь он сравнивается с тем, что уже лежит в базе: неизменные записи остаются
как есть (сохраняют id), изменённые обновляются, лишние удаляются, новые создаются. Всё в одной
транзакции: либо ячейка сохранена целиком, либо не изменилась.
"""
from collections import defaultdict
from datetime import time

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.template.loader import render_to_string

from .cellinput import CellError, format_cell, parse_cell
from .checks import HOURS_NORM, check_schedule
from .grids import ZERO, shift_item
from .models import Cabinet, Shift, TimeKind
from .norms import MonthNorms


class CellRejected(Exception):
    """Ввод не принят; ячейка не изменилась. Сообщение показывается человеку."""


class CellConflict(Exception):
    """Пока человек печатал, ячейку изменили. current: что в ячейке сейчас."""

    def __init__(self, current):
        super().__init__(current)
        self.current = current


def cell_shifts(schedule, assignment_id, day):
    shifts = Shift.objects.filter(schedule=schedule, assignment_id=assignment_id, date=day).select_related(
        "kind", "cabinet"
    )
    return sorted(shifts, key=lambda s: (s.start or time.min, s.id))


def default_cabinet_for(schedule, assignment):
    """Кабинет для смены без кабинета в тексте: последняя смена строки, иначе самый частый у врача."""
    last = (
        Shift.objects.filter(schedule=schedule, assignment=assignment, kind__is_working=True, cabinet__isnull=False)
        .select_related("cabinet")
        .order_by("-date", "-start", "-id")
        .first()
    )
    if last is not None:
        return last.cabinet
    frequent = (
        Shift.objects.filter(assignment__doctor_id=assignment.doctor_id, kind__is_working=True, cabinet__isnull=False)
        .values("cabinet")
        .annotate(total=Count("id"))
        .order_by("-total", "cabinet")
        .first()
    )
    return Cabinet.objects.filter(pk=frequent["cabinet"]).first() if frequent else None


def _entry_key(entry):
    return (entry.kind.pk, entry.start, entry.end, entry.cabinet.pk if entry.cabinet else None)


def _shift_key(shift):
    return (shift.kind_id, shift.start, shift.end, shift.cabinet_id)


def apply_cell(schedule, row, day, raw, expected=None):
    """Заменить записи ячейки по тексту. Возвращает каноническое значение ячейки.

    expected: значение ячейки, которое видел человек, когда начал править. Не совпало с текущим:
    CellConflict. Без expected сравнение пропускается.
    Ввод не принят: CellRejected. В обоих случаях ничего не записано.
    """
    if (day.year, day.month) != (schedule.year, schedule.month):
        raise CellRejected("Эта дата не входит в месяц графика")
    assignment = row.assignment
    with transaction.atomic():
        existing = cell_shifts(schedule, assignment.id, day)
        current = format_cell(existing)
        if expected is not None and expected.strip() != current:
            raise CellConflict(current)

        cabinets = list(Cabinet.objects.filter(is_active=True))
        kinds = list(TimeKind.objects.filter(is_active=True))
        parsed = parse_cell(raw, cabinets, kinds, lambda: default_cabinet_for(schedule, assignment))
        if isinstance(parsed, CellError):
            raise CellRejected(parsed.message)

        # неизменные записи остаются, остальные существующие переиспользуются по порядку
        wanted = list(parsed)
        keep, spare = [], []
        for shift in existing:
            match = next((e for e in wanted if _entry_key(e) == _shift_key(shift)), None)
            if match is not None:
                wanted.remove(match)
                keep.append(shift)
            else:
                spare.append(shift)
        try:
            for entry in wanted:
                shift = spare.pop(0) if spare else Shift(schedule=schedule, assignment=assignment, date=day)
                shift.kind, shift.start, shift.end, shift.cabinet = entry.kind, entry.start, entry.end, entry.cabinet
                shift.save()
                keep.append(shift)
            for shift in spare:
                shift.delete()
        except ValidationError as error:
            raise CellRejected("; ".join(error.messages)) from error
        return format_cell(keep)


def cell_payload(schedule, row, day, value, page_path=None):
    """Состояние ячейки после сохранения: значение, содержимое для показа, вид.

    html: то же содержимое ячейки, что на странице (общий шаблон _cell_content.html); скрипт подставляет его как есть.
    page_path: адрес страницы графика для ссылок правки (параметр next).
    """
    shifts = cell_shifts(schedule, row.assignment_id, day)
    if not shifts:
        kind = "off"
    elif any(s.kind.is_working for s in shifts):
        kind = "shift"
    else:
        kind = "absence"
    full_items = [shift_item(s, True) for s in shifts]
    return {
        "value": value,
        "kind": kind,
        "items": [{"label": i["label"], "cabinet": i["cabinet"]} for i in full_items],
        "html": render_to_string("schedule/_cell_content.html", {"items": full_items, "page_path": page_path or ""}),
        "shift_id": shifts[0].id if shifts else None,
    }


def row_totals(schedule, row):
    """Дни, часы, норма и отклонение строки: те же значения, что показывает сетка."""
    shifts = Shift.objects.filter(schedule=schedule, assignment_id=row.assignment_id, kind__is_working=True)
    shifts = shifts.select_related("kind")
    planned = sum((s.hours for s in shifts), ZERO)
    worked_days = len({s.date for s in shifts})
    norm = MonthNorms(schedule.year, schedule.month).hours(row.assignment, rate=row.rate)
    return {
        "days": worked_days,
        "planned": str(planned),
        "norm": None if norm is None else str(norm),
        "deviation": None if norm is None else str(planned - norm),
    }


def issue_state(schedule):
    """Какие ячейки и строки графика сейчас с ошибкой и тексты ошибок для списка под сеткой."""
    issues = check_schedule(schedule)
    shift_ids = {shift_id for issue in issues for shift_id in issue.shift_ids}
    cells = defaultdict(set)
    for shift_id, assignment_id, day in Shift.objects.filter(schedule=schedule, id__in=shift_ids).values_list(
        "id", "assignment_id", "date"
    ):
        cells[assignment_id].add(day.isoformat())
    return {
        "cells": [
            {"assignment": assignment_id, "date": day} for assignment_id, days in cells.items() for day in sorted(days)
        ],
        "norm_rows": sorted({i.assignment_id for i in issues if i.code == HOURS_NORM}),
        "messages": [issue.message for issue in issues],
    }
