"""Состав строк графика: добавить врача, убрать, переставить, изменить ставку и профессию, скопировать состав.

Правила целиком живут здесь, а не в представлениях: так их проверяют тесты и ими пользуются и страницы,
и административный интерфейс.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q

from .models import Assignment, Schedule, ScheduleRow, Shift

MIN_RATE = Decimal("0.01")
MAX_RATE = Decimal("2.00")


class RowError(Exception):
    """Ошибка с понятным пользователю текстом."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class RowExists(RowError):
    """Этот врач с этой профессией уже есть в графике."""

    def __init__(self, row):
        super().__init__(f"{row.assignment.doctor.short_name} ({row.assignment.specialty}) уже есть в графике.")
        self.row = row


class ConfirmRequired(RowError):
    """В строке есть смены: для удаления нужно подтвердить их число."""

    def __init__(self, shifts):
        super().__init__(f"В строке {shifts} смен за этот месяц, их нужно подтвердить.")
        self.shifts = shifts


def validate_rate(rate):
    if rate is None or not (MIN_RATE <= rate <= MAX_RATE):
        raise RowError("Ставка должна быть от 0,01 до 2.")
    return rate


def renumber(schedule):
    """Порядковые номера 1..n по текущему порядку строк."""
    for index, row in enumerate(ScheduleRow.objects.filter(schedule=schedule).order_by("sort_order", "id"), start=1):
        if row.sort_order != index:
            ScheduleRow.objects.filter(pk=row.pk).update(sort_order=index)


def _assignment_for(schedule, doctor, specialty, rate):
    """Assignment отделения для пары врач и профессия: берётся существующий или создаётся новый."""
    assignment, created = Assignment.objects.get_or_create(
        doctor=doctor,
        department=schedule.department,
        specialty=specialty,
        defaults={"rate": rate},
    )
    if not created and not assignment.is_active:
        assignment.is_active = True
        assignment.save(update_fields=["is_active"])
    return assignment


@transaction.atomic
def add_row(schedule, doctor, specialty, rate, position=None):
    """Добавляет врача в график на заданное место (0 — первым, по умолчанию в конец)."""
    validate_rate(rate)
    assignment = _assignment_for(schedule, doctor, specialty, rate)
    existing = ScheduleRow.objects.filter(schedule=schedule, assignment=assignment).first()
    if existing is not None:
        raise RowExists(existing)
    count = ScheduleRow.objects.filter(schedule=schedule).count()
    place = count if position is None else max(0, min(int(position), count))
    ScheduleRow.objects.filter(schedule=schedule, sort_order__gt=place).update(sort_order=F("sort_order") + 1)
    row = ScheduleRow.objects.create(schedule=schedule, assignment=assignment, rate=rate, sort_order=place + 1)
    renumber(schedule)
    row.refresh_from_db()
    return row


@transaction.atomic
def remove_row(row, confirm=None):
    """Убирает строку. Если в ней есть смены, нужно передать их точное число; смены месяца удаляются."""
    shifts = Shift.objects.filter(schedule=row.schedule, assignment=row.assignment)
    count = shifts.count()
    if count and confirm != count:
        raise ConfirmRequired(count)
    shifts.delete()
    schedule = row.schedule
    row.delete()
    renumber(schedule)
    return count


@transaction.atomic
def move_row(row, direction=None, position=None):
    """Переставляет строку на шаг вверх или вниз либо на заданное место."""
    ordered = list(ScheduleRow.objects.filter(schedule=row.schedule).order_by("sort_order", "id"))
    index = next(i for i, r in enumerate(ordered) if r.pk == row.pk)
    if position is not None:
        target = max(0, min(int(position), len(ordered) - 1))
    elif direction == "up":
        target = max(0, index - 1)
    elif direction == "down":
        target = min(len(ordered) - 1, index + 1)
    else:
        raise RowError("Не понял, куда переместить строку.")
    ordered.insert(target, ordered.pop(index))
    for number, item in enumerate(ordered, start=1):
        if item.sort_order != number:
            ScheduleRow.objects.filter(pk=item.pk).update(sort_order=number)
    row.refresh_from_db()
    return row


@transaction.atomic
def update_row(row, rate=None, specialty=None):
    """Ставка и профессия строки только в этом месяце; смены переносятся на Assignment с новой профессией."""
    if rate is not None:
        validate_rate(rate)
        row.rate = rate
    if specialty is not None and specialty.pk != row.assignment.specialty_id:
        old = row.assignment
        new = _assignment_for(row.schedule, old.doctor, specialty, row.rate)
        clash = ScheduleRow.objects.filter(schedule=row.schedule, assignment=new).exclude(pk=row.pk).first()
        if clash is not None:
            raise RowExists(clash)
        Shift.objects.filter(schedule=row.schedule, assignment=old).update(assignment=new)
        row.assignment = new
    row.save()
    return row


@transaction.atomic
def copy_roster(schedule):
    """Заполняет новый график: состав и порядок предыдущего графика отделения, иначе действующие врачи.

    Ничего не делает, если в графике уже есть строки. Возвращает созданные строки.
    """
    if ScheduleRow.objects.filter(schedule=schedule).exists():
        return []
    earlier = Q(year__lt=schedule.year) | Q(year=schedule.year, month__lt=schedule.month)
    previous = (
        Schedule.objects.filter(department=schedule.department, rows__isnull=False)
        .filter(earlier)
        .order_by("-year", "-month")
        .first()
    )
    created = []
    if previous is not None:
        source = [
            (r.assignment, r.rate)
            for r in ScheduleRow.objects.filter(schedule=previous)
            .select_related("assignment__doctor", "assignment__specialty")
            .order_by("sort_order", "id")
            if r.assignment.is_active
        ]
    else:
        assignments = sorted(
            Assignment.objects.filter(department=schedule.department, is_active=True).select_related(
                "doctor", "specialty"
            ),
            key=lambda a: (a.doctor.last_name, a.doctor.first_name, a.doctor.patronymic, a.specialty.name),
        )
        source = [(a, a.rate) for a in assignments]
    for position, (assignment, rate) in enumerate(source, start=1):
        created.append(
            ScheduleRow.objects.create(schedule=schedule, assignment=assignment, rate=rate, sort_order=position)
        )
    return created
