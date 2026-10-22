"""Норма часов, план и дефицит по Assignment за месяц."""
from decimal import ROUND_HALF_UP, Decimal

from .models import MonthNorm, Shift, SpecialtyMonthNorm

CENT = Decimal("0.01")


def norm_hours(assignment, year, month):
    """Норма на месяц: норма профессии (если задана) или общая норма месяца, умноженная на ставку.

    Возвращает None, если ни одной нормы на этот месяц нет.
    """
    base = (
        SpecialtyMonthNorm.objects.filter(specialty=assignment.specialty_id, year=year, month=month)
        .values_list("hours", flat=True)
        .first()
    )
    if base is None:
        base = MonthNorm.objects.filter(year=year, month=month).values_list("hours", flat=True).first()
    if base is None:
        return None
    return (base * assignment.rate).quantize(CENT, rounding=ROUND_HALF_UP)


def planned_hours(assignment, year, month):
    """Сумма часов рабочих смен Assignment за месяц."""
    shifts = Shift.objects.filter(
        assignment=assignment, date__year=year, date__month=month, kind__is_working=True
    ).select_related("kind")
    return sum((shift.hours for shift in shifts), Decimal("0.00"))


def deficit_hours(assignment, year, month):
    """Норма минус план; None, если нормы нет."""
    norm = norm_hours(assignment, year, month)
    if norm is None:
        return None
    return norm - planned_hours(assignment, year, month)
