"""Проверки графика. Чистые функции без привязки к страницам.

Проверки ничего не блокируют: они только возвращают список ошибок, который
показывается в ячейках и в списке ошибок месяца.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q

from .models import Assignment, Shift
from .norms import MonthNorms, planned_hours_by_assignment

SHIFT_TOO_SHORT = "shift_too_short"
SHIFT_TOO_LONG = "shift_too_long"
DOCTOR_DOUBLE_BOOKED = "doctor_double_booked"
WORK_ON_ABSENCE = "work_on_absence"
CABINET_OVERLAP = "cabinet_overlap"
HOURS_NORM = "hours_norm"


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    shift_ids: tuple = ()
    assignment_id: int | None = None


def _hours(value: Decimal) -> str:
    """Decimal('5.50') -> '5,5'"""
    return format(value.normalize(), "f").replace(".", ",")


def _interval(shift) -> str:
    return f"{shift.start:%H:%M}–{shift.end:%H:%M}"


def _working(shifts):
    return [s for s in shifts if s.kind.is_working and s.start and s.end]


def _overlap(a, b) -> bool:
    """Смены встык (конец одной равен началу другой) пересечением не считаются."""
    return a.start < b.end and b.start < a.end


def _pairs(items):
    for i, first in enumerate(items):
        for second in items[i + 1 :]:
            yield first, second


def check_shift_length(shifts):
    """Длина рабочей смены в границах правила профессии или своих границ Assignment."""
    issues = []
    for shift in _working(shifts):
        minimum, maximum = shift.assignment.shift_limits()
        hours = shift.hours
        who = f"{shift.assignment.doctor.short_name}, {shift.date:%d.%m}"
        if minimum is not None and hours < minimum:
            issues.append(
                Issue(
                    SHIFT_TOO_SHORT,
                    f"{who}: смена {_hours(hours)} ч, меньше допустимых {_hours(minimum)} ч",
                    (shift.id,),
                    shift.assignment_id,
                )
            )
        if maximum is not None and hours > maximum:
            issues.append(
                Issue(
                    SHIFT_TOO_LONG,
                    f"{who}: смена {_hours(hours)} ч, больше допустимых {_hours(maximum)} ч",
                    (shift.id,),
                    shift.assignment_id,
                )
            )
    return issues


def check_doctor_overlap(shifts):
    """Один врач не записан одновременно в двух местах (в любых своих Assignment)."""
    groups = defaultdict(list)
    for shift in _working(shifts):
        groups[(shift.assignment.doctor_id, shift.date)].append(shift)
    issues = []
    for group in groups.values():
        for first, second in _pairs(sorted(group, key=lambda s: (s.start, s.id))):
            if _overlap(first, second):
                doctor = first.assignment.doctor
                issues.append(
                    Issue(
                        DOCTOR_DOUBLE_BOOKED,
                        f"{doctor.short_name}, {first.date:%d.%m}: смены "
                        f"{_interval(first)} и {_interval(second)} пересекаются",
                        tuple(sorted((first.id, second.id))),
                    )
                )
    return issues


def check_work_on_absence(shifts):
    """В день нерабочего вида (отпуск, больничный...) у того же Assignment нет рабочей смены."""
    groups = defaultdict(list)
    for shift in shifts:
        groups[(shift.assignment_id, shift.date)].append(shift)
    issues = []
    for group in groups.values():
        absences = [s for s in group if not s.kind.is_working]
        if absences and any(s.kind.is_working for s in group):
            doctor = group[0].assignment.doctor
            kinds = ", ".join(sorted({s.kind.name for s in absences}))
            issues.append(
                Issue(
                    WORK_ON_ABSENCE,
                    f"{doctor.short_name}, {group[0].date:%d.%m}: рабочая смена в день «{kinds}»",
                    tuple(sorted(s.id for s in group)),
                    group[0].assignment_id,
                )
            )
    return issues


def check_cabinet_overlap(shifts):
    """Кабинет не занят двумя разными врачами одновременно, кроме кабинетов с is_shared."""
    groups = defaultdict(list)
    for shift in _working(shifts):
        if shift.cabinet_id and not shift.cabinet.is_shared:
            groups[(shift.cabinet_id, shift.date)].append(shift)
    issues = []
    for group in groups.values():
        for first, second in _pairs(sorted(group, key=lambda s: (s.start, s.id))):
            if first.assignment.doctor_id == second.assignment.doctor_id:
                continue  # пересечение смен одного врача ловит check_doctor_overlap
            if _overlap(first, second):
                issues.append(
                    Issue(
                        CABINET_OVERLAP,
                        f"Кабинет {first.cabinet}, {first.date:%d.%m}: "
                        f"{first.assignment.doctor.short_name} ({_interval(first)}) и "
                        f"{second.assignment.doctor.short_name} ({_interval(second)}) одновременно",
                        tuple(sorted((first.id, second.id))),
                    )
                )
    return issues


def check_hours_norm(schedule):
    """Часы за месяц совпадают с нормой. Проверяются Assignment, у которых есть записи в графике."""
    assignments = (
        Assignment.objects.filter(shifts__schedule=schedule)
        .distinct()
        .select_related("doctor", "specialty")
    )
    assignments = list(assignments)
    norms = MonthNorms(schedule.year, schedule.month)
    planned_by_id = planned_hours_by_assignment([a.id for a in assignments], schedule.year, schedule.month)
    issues = []
    for assignment in assignments:
        norm = norms.hours(assignment)
        if norm is None:
            continue
        planned = planned_by_id[assignment.id]
        if planned == norm:
            continue
        difference = norm - planned
        verdict = (
            f"не хватает {_hours(difference)} ч" if difference > 0 else f"лишних {_hours(-difference)} ч"
        )
        issues.append(
            Issue(
                HOURS_NORM,
                f"{assignment.doctor.short_name}: запланировано {_hours(planned)} ч "
                f"при норме {_hours(norm)} ч, {verdict}",
                (),
                assignment.id,
            )
        )
    return issues


def _month_shifts(schedule):
    return Shift.objects.filter(
        date__year=schedule.year, date__month=schedule.month
    ).select_related("assignment__doctor", "assignment__specialty", "kind", "cabinet").prefetch_related(
        "assignment__specialty__length_rules"
    )


def check_schedule(schedule):
    """Все проверки по графику отделения.

    Пересечения врача и кабинета ищутся среди смен всего месяца у тех же врачей
    и в тех же кабинетах, в том числе из графиков других отделений.
    Возвращаются только ошибки, в которых участвует хотя бы одна смена этого графика.
    """
    own = list(_month_shifts(schedule).filter(schedule=schedule))
    own_ids = {s.id for s in own}
    doctor_ids = {s.assignment.doctor_id for s in own}
    cabinet_ids = {s.cabinet_id for s in own if s.cabinet_id}
    related = {
        s.id: s
        for s in _month_shifts(schedule).filter(
            Q(assignment__doctor_id__in=doctor_ids) | Q(cabinet_id__in=cabinet_ids)
        )
    }
    related.update({s.id: s for s in own})
    everything = list(related.values())

    issues = []
    issues += check_shift_length(own)
    issues += check_work_on_absence(own)
    issues += check_doctor_overlap(everything)
    issues += check_cabinet_overlap(everything)
    issues = [issue for issue in issues if own_ids.intersection(issue.shift_ids)]
    issues += check_hours_norm(schedule)  # относится к Assignment, а не к смене
    return issues
