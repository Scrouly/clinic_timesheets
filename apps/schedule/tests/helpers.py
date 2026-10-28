"""Общие заготовки для тестов графиков."""
from datetime import date, time
from decimal import Decimal

from apps.accounts.models import AccessLevel, DepartmentAccess, Role, User
from apps.core.models import Department
from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import (
    Assignment,
    Cabinet,
    Doctor,
    Schedule,
    ScheduleRow,
    Shift,
    ShiftLengthRule,
    Specialty,
    TimeKind,
)


def make_access_user(username, role=Role.HEAD, edit=(), view=()):
    """Пользователь с правами на отделения: edit — редактирование, view — только просмотр."""
    user = User.objects.create_user(
        username, password=PASSWORD, role=role, last_name=username.title(), first_name="Тест"
    )
    for department in edit:
        DepartmentAccess.objects.create(user=user, department=department, level=AccessLevel.EDIT)
    for department in view:
        DepartmentAccess.objects.create(user=user, department=department, level=AccessLevel.VIEW)
    return user


def t(text):
    """'9:00' -> time(9, 0)"""
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


class ScheduleTestMixin:
    """Примесь к TestCase: отделения, кабинеты, виды времени и фабрики, январь 2026."""

    def setUpData(self):
        self.dept_a = Department.objects.create(name="Отделение А")
        self.dept_b = Department.objects.create(name="Отделение Б")
        self.cab1 = Cabinet.objects.create(name="301")
        self.cab2 = Cabinet.objects.create(name="302")
        self.surgeon = Specialty.objects.create(name="Хирург")
        self.uzd = Specialty.objects.create(name="Врач УЗД")
        # неполная ставка: не более 5,5 часа; полная и выше: не менее 5,6 часа
        ShiftLengthRule.objects.create(
            specialty=self.uzd, rate_from=Decimal("0"), rate_to=Decimal("1"), max_hours=Decimal("5.5")
        )
        ShiftLengthRule.objects.create(specialty=self.uzd, rate_from=Decimal("1"), min_hours=Decimal("5.6"))
        self.work = TimeKind.objects.create(name="Работа", short_label="Р", is_working=True)
        self.vacation = TimeKind.objects.create(name="Отпуск", short_label="ОТП")
        self._doctor_counter = 0

    def make_doctor(self, last_name=None):
        self._doctor_counter += 1
        return Doctor.objects.create(last_name=last_name or f"Врач{self._doctor_counter}", first_name="Иван")

    def make_assignment(self, doctor=None, department=None, specialty=None, rate="1", **kwargs):
        return Assignment.objects.create(
            doctor=doctor or self.make_doctor(),
            department=department or self.dept_a,
            specialty=specialty or self.surgeon,
            rate=Decimal(rate),
            **kwargs,
        )

    def make_shift(self, assignment, start, end, day=12, cabinet=None, kind=None):
        """Смена в январе 2026; график отделения берётся или создаётся сам."""
        schedule, _ = Schedule.objects.get_or_create(
            department=assignment.department, year=2026, month=1
        )
        kind = kind or self.work
        if kind.is_working:
            return Shift.objects.create(
                schedule=schedule,
                assignment=assignment,
                date=date(2026, 1, day),
                kind=kind,
                start=t(start),
                end=t(end),
                cabinet=cabinet or self.cab1,
            )
        return Shift.objects.create(
            schedule=schedule, assignment=assignment, date=date(2026, 1, day), kind=kind
        )

    def make_schedule(self, department=None, year=2026, month=1):
        schedule, _ = Schedule.objects.get_or_create(
            department=department or self.dept_a, year=year, month=month
        )
        return schedule

    def make_row(self, assignment, schedule=None, rate=None):
        """Строка графика врача; график января 2026 берётся или создаётся сам."""
        schedule = schedule or self.make_schedule(assignment.department)
        row = ScheduleRow.ensure(schedule, assignment)
        if rate is not None:
            row.rate = Decimal(rate)
            row.save()
        return row
