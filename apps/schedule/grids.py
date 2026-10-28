"""Сборщики сеток: из одной таблицы смен строят два вида графика.

Обе сетки читают Shift и ничего не хранят, поэтому правка в одном виде
сразу видна в другом.
"""
import calendar
from collections import defaultdict
from datetime import date, time
from decimal import Decimal

from django.utils import timezone

from .cellinput import format_cell
from .checks import HOURS_NORM, check_schedule
from .models import Cabinet, CalendarDay, DayKind, ScheduleRow, Shift
from .norms import MonthNorms

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
ZERO = Decimal("0.00")


def month_days(year, month):
    """Дни месяца; выходной определяется календарём, а без отметки в нём субботой и воскресеньем."""
    marks = dict(
        CalendarDay.objects.filter(date__year=year, date__month=month).values_list("date", "kind")
    )
    today = timezone.localdate()
    days = []
    for number in range(1, calendar.monthrange(year, month)[1] + 1):
        day = date(year, month, number)
        kind = marks.get(day)
        is_weekend = day.weekday() >= 5 if kind is None else kind in (DayKind.WEEKEND, DayKind.HOLIDAY)
        days.append(
            {
                "number": number,
                "date": day,
                "weekday": WEEKDAYS[day.weekday()],
                "is_weekend": is_weekend,
                "is_holiday": kind == DayKind.HOLIDAY,
                "is_today": day == today,
            }
        )
    return days


def shift_item(shift, editable):
    working = shift.kind.is_working
    return {
        "id": shift.id,
        "label": f"{shift.start:%H:%M}–{shift.end:%H:%M}" if working else shift.kind.short_label,
        "cabinet": shift.cabinet.name if working and shift.cabinet_id else "",
        "working": working,
        "editable": editable,
    }


def make_cell(day, shifts, editable_of, issue_shift_ids, empty_editable=False):
    shifts = sorted(shifts, key=lambda s: (s.start or time.min, s.id))
    items = [shift_item(shift, editable_of(shift)) for shift in shifts]
    if not shifts:
        kind = "off"
    elif any(s.kind.is_working for s in shifts):
        kind = "shift"
    else:
        kind = "absence"
    return {
        "date": day["date"],
        "number": day["number"],
        "weekend": day["is_weekend"],
        "holiday": day["is_holiday"],
        "today": day["is_today"],
        "items": items,
        "kind": kind,
        "value": format_cell(shifts),  # каноническая запись: что видит и править человек в ячейке
        "hours": sum((s.hours for s in shifts), ZERO),
        "editable": all(item["editable"] for item in items) if items else empty_editable,
        "has_issue": any(s.id in issue_shift_ids for s in shifts),
    }


def _rate_text(rate):
    return format(rate.normalize(), "f").replace(".", ",")


def build_department_grid(schedule, user):
    """Вид по отделению: строки это врачи отделения (Assignment), столбцы это дни месяца."""
    can_edit = user.editable_departments().filter(pk=schedule.department_id).exists()
    issues = check_schedule(schedule)
    issue_shift_ids = {shift_id for issue in issues for shift_id in issue.shift_ids}
    norm_issue_ids = {issue.assignment_id for issue in issues if issue.code == HOURS_NORM}

    by_cell = defaultdict(list)
    for shift in Shift.objects.filter(schedule=schedule).select_related("kind", "cabinet"):
        by_cell[(shift.assignment_id, shift.date)].append(shift)

    schedule_rows = ScheduleRow.objects.filter(schedule=schedule).select_related(
        "assignment__doctor", "assignment__specialty"
    )
    shift_counts = defaultdict(int)
    for (assignment_id, _day), cell_shifts in by_cell.items():
        shift_counts[assignment_id] += len(cell_shifts)

    days = month_days(schedule.year, schedule.month)
    norms = MonthNorms(schedule.year, schedule.month)
    rows = []
    for schedule_row in schedule_rows:
        assignment = schedule_row.assignment
        cells = [
            make_cell(
                day,
                by_cell.get((assignment.id, day["date"]), []),
                lambda shift: can_edit,
                issue_shift_ids,
                empty_editable=can_edit,
            )
            for day in days
        ]
        planned = sum((cell["hours"] for cell in cells), ZERO)
        norm = norms.hours(assignment, rate=schedule_row.rate)
        rows.append(
            {
                "row": schedule_row,
                "assignment": assignment,
                "name": assignment.doctor.short_name,
                "position": f"{assignment.specialty} ({_rate_text(schedule_row.rate)} ст.)",
                "shift_count": shift_counts.get(assignment.id, 0),
                "cells": cells,
                "worked_days": sum(1 for cell in cells if cell["kind"] == "shift"),
                "planned": planned,
                "norm": norm,
                "deficit": None if norm is None else norm - planned,
                "deviation": None if norm is None else planned - norm,
                "has_norm_issue": assignment.id in norm_issue_ids,
            }
        )
    return {"schedule": schedule, "days": days, "rows": rows, "can_edit": can_edit, "issues": issues}


def build_cabinet_grid(year, month, user, issues_only=False):
    """Общий вид по кабинетам: строки это дни, столбцы это кабинеты, внутри кабинета врачи.

    В вид входят кабинеты с флагом in_cabinet_schedule и все рабочие смены в них,
    из любого отделения. Редактировать можно только смены отделений с правом «редактирование».
    При issues_only в строках остаются только дни, где есть накладка или ошибка.
    """
    cabinets = list(Cabinet.objects.filter(in_cabinet_schedule=True, is_active=True))
    editable_ids = set(user.editable_departments().values_list("pk", flat=True))
    shifts = list(
        Shift.objects.filter(
            date__year=year, date__month=month, kind__is_working=True, cabinet__in=cabinets
        ).select_related("assignment__doctor", "kind", "cabinet", "schedule__department")
    )

    issue_shift_ids = set()
    for schedule in {shift.schedule_id: shift.schedule for shift in shifts}.values():
        for issue in check_schedule(schedule):
            issue_shift_ids.update(issue.shift_ids)

    doctors = {}
    by_cabinet = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # кабинет -> врач -> дата
    for shift in shifts:
        doctor = shift.assignment.doctor
        doctors[doctor.id] = doctor
        by_cabinet[shift.cabinet_id][doctor.id][shift.date].append(shift)

    def editable_of(shift):
        return shift.assignment.department_id in editable_ids

    days = month_days(year, month)
    entries = []
    for cabinet in cabinets:
        doctor_ids = sorted(
            by_cabinet.get(cabinet.id, {}),
            key=lambda d: (doctors[d].last_name, doctors[d].first_name, doctors[d].patronymic, d),
        )
        doctor_entries = []
        for doctor_id in doctor_ids:
            by_day = by_cabinet[cabinet.id][doctor_id]
            cells = [
                make_cell(day, by_day.get(day["date"], []), editable_of, issue_shift_ids) for day in days
            ]
            doctor_entries.append(
                {
                    "doctor": doctors[doctor_id],
                    "cells": cells,
                    "total": sum((cell["hours"] for cell in cells), ZERO),
                }
            )
        day_totals = [
            sum((entry["cells"][index]["hours"] for entry in doctor_entries), ZERO)
            for index in range(len(days))
        ]
        entries.append(
            {
                "cabinet": cabinet,
                "doctors": doctor_entries,
                "day_totals": day_totals,
                "total": sum((entry["total"] for entry in doctor_entries), ZERO),
            }
        )

    day_rows = [
        {
            "day": day,
            "groups": [
                {
                    "cabinet": entry["cabinet"],
                    "cells": [doctor["cells"][index] for doctor in entry["doctors"]],
                    "total": entry["day_totals"][index],
                }
                for entry in entries
            ],
        }
        for index, day in enumerate(days)
    ]
    issue_cells = sum(
        1 for entry in entries for doctor in entry["doctors"] for cell in doctor["cells"] if cell["has_issue"]
    )
    if issues_only:
        day_rows = [
            row for row in day_rows if any(cell["has_issue"] for group in row["groups"] for cell in group["cells"])
        ]
    return {
        "year": year,
        "month": month,
        "days": days,
        "cabinets": entries,
        "day_rows": day_rows,
        "can_edit": bool(editable_ids),
        "issue_cells": issue_cells,
        "issues_only": issues_only,
    }
