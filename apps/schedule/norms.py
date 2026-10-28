"""Норма часов, план и дефицит по Assignment за месяц."""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from .models import MonthNorm, Shift, SpecialtyMonthNorm

CENT = Decimal("0.01")


class MonthNorms:
    """Нормы месяца, прочитанные двумя запросами сразу для всех профессий.

    Нужны там, где норма считается для многих Assignment подряд: один запрос на врача
    превращал бы страницу в сотни обращений к базе.
    """

    def __init__(self, year, month):
        self.general = MonthNorm.objects.filter(year=year, month=month).values_list("hours", flat=True).first()
        self.by_specialty = dict(
            SpecialtyMonthNorm.objects.filter(year=year, month=month).values_list("specialty_id", "hours")
        )

    def hours(self, assignment, rate=None):
        """Норма профессии (если задана) или общая норма месяца, умноженная на ставку; None, если норм нет.

        rate: ставка месяца из строки графика; без неё берётся ставка по умолчанию у Assignment.
        """
        base = self.by_specialty.get(assignment.specialty_id, self.general)
        if base is None:
            return None
        return (base * (assignment.rate if rate is None else rate)).quantize(CENT, rounding=ROUND_HALF_UP)


def norm_hours(assignment, year, month):
    """Норма на месяц для одного Assignment; None, если ни одной нормы на этот месяц нет."""
    return MonthNorms(year, month).hours(assignment)


def planned_hours_by_assignment(assignment_ids, year, month):
    """{assignment_id: сумма часов рабочих смен за месяц} одним запросом."""
    shifts = Shift.objects.filter(
        assignment_id__in=list(assignment_ids), date__year=year, date__month=month, kind__is_working=True
    ).select_related("kind")
    totals = defaultdict(lambda: Decimal("0.00"))
    for shift in shifts:
        totals[shift.assignment_id] += shift.hours
    return totals


def planned_hours(assignment, year, month):
    """Сумма часов рабочих смен Assignment за месяц."""
    return planned_hours_by_assignment([assignment.id], year, month)[assignment.id]


def deficit_hours(assignment, year, month):
    """Норма минус план; None, если нормы нет."""
    norm = norm_hours(assignment, year, month)
    if norm is None:
        return None
    return norm - planned_hours(assignment, year, month)
