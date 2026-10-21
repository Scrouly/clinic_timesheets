from datetime import date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import Department
from apps.schedule.models import (
    Assignment,
    Cabinet,
    Doctor,
    Schedule,
    Shift,
    Specialty,
    TimeKind,
)


class ShiftTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Хирургическое отделение")
        self.other_dept = Department.objects.create(name="Диагностическое отделение")
        self.cabinet = Cabinet.objects.create(name="301")
        self.specialty = Specialty.objects.create(name="Хирург")
        self.doctor = Doctor.objects.create(last_name="Орлов", first_name="Андрей")
        self.assignment = Assignment.objects.create(
            doctor=self.doctor, department=self.dept, specialty=self.specialty, rate=Decimal("1")
        )
        self.schedule = Schedule.objects.create(department=self.dept, year=2026, month=1)
        self.work = TimeKind.objects.create(name="Работа", short_label="Р", is_working=True)
        self.vacation = TimeKind.objects.create(name="Отпуск", short_label="ОТП")

    def shift(self, **kwargs):
        defaults = dict(
            schedule=self.schedule,
            assignment=self.assignment,
            date=date(2026, 1, 12),
            kind=self.work,
            start=time(8, 0),
            end=time(14, 40),
            cabinet=self.cabinet,
        )
        defaults.update(kwargs)
        return Shift(**defaults)

    def test_working_shift_requires_start_end_cabinet(self):
        for field in ("start", "end", "cabinet"):
            with self.assertRaises(ValidationError, msg=field) as ctx:
                self.shift(**{field: None}).full_clean()
            self.assertIn(field, ctx.exception.message_dict)

    def test_non_working_shift_rejects_times_and_cabinet(self):
        self.shift(kind=self.vacation, start=None, end=None, cabinet=None).full_clean()
        for field, value in (("start", time(8, 0)), ("end", time(9, 0)), ("cabinet", self.cabinet)):
            kwargs = dict(kind=self.vacation, start=None, end=None, cabinet=None)
            kwargs[field] = value
            with self.assertRaises(ValidationError, msg=field) as ctx:
                self.shift(**kwargs).full_clean()
            self.assertIn(field, ctx.exception.message_dict)

    def test_end_must_be_after_start(self):
        for end in (time(8, 0), time(7, 0)):
            with self.assertRaises(ValidationError, msg=end):
                self.shift(end=end).full_clean()

    def test_shift_cannot_cross_midnight(self):
        with self.assertRaises(ValidationError) as ctx:
            self.shift(start=time(22, 0), end=time(0, 0)).full_clean()
        self.assertIn("Смена не может переходить через полночь", str(ctx.exception))

    def test_hours_rounded_to_hundredths(self):
        self.assertEqual(self.shift().hours, Decimal("6.67"))
        vacation = self.shift(kind=self.vacation, start=None, end=None, cabinet=None)
        self.assertEqual(vacation.hours, Decimal("0"))

    def test_assignment_department_must_match_schedule(self):
        foreign = Assignment.objects.create(
            doctor=self.doctor,
            department=self.other_dept,
            specialty=self.specialty,
            rate=Decimal("1"),
        )
        with self.assertRaises(ValidationError) as ctx:
            self.shift(assignment=foreign).full_clean()
        self.assertIn("assignment", ctx.exception.message_dict)

    def test_date_must_be_in_schedule_month(self):
        with self.assertRaises(ValidationError) as ctx:
            self.shift(date=date(2026, 2, 3)).full_clean()
        self.assertIn("date", ctx.exception.message_dict)

    def test_save_runs_validation(self):
        with self.assertRaises(ValidationError):
            self.shift(end=time(7, 0)).save()
        self.assertEqual(Shift.objects.count(), 0)

    def test_db_constraint_end_after_start(self):
        bad = self.shift(end=time(7, 0))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Shift.objects.bulk_create([bad])
