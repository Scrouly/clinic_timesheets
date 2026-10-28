import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.schedule.models import Assignment, Schedule, ScheduleRow

from .helpers import ScheduleTestMixin


class ScheduleRowModelTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"), rate="0.75")

    def test_pair_schedule_assignment_is_unique(self):
        ScheduleRow.objects.create(schedule=self.schedule, assignment=self.assignment, rate=Decimal("0.75"))
        with self.assertRaises((ValidationError, IntegrityError)):
            ScheduleRow(schedule=self.schedule, assignment=self.assignment, rate=Decimal("1")).save()

    def test_assignment_must_belong_to_the_schedule_department(self):
        foreign = self.make_assignment(doctor=self.make_doctor("Белов"), department=self.dept_b)
        with self.assertRaises(ValidationError):
            ScheduleRow(schedule=self.schedule, assignment=foreign, rate=Decimal("1")).save()

    def test_ensure_creates_with_assignment_rate_and_next_order(self):
        second = self.make_assignment(doctor=self.make_doctor("Белов"), rate="1")
        first_row = ScheduleRow.ensure(self.schedule, self.assignment)
        second_row = ScheduleRow.ensure(self.schedule, second)
        self.assertEqual(first_row.rate, Decimal("0.75"))
        self.assertEqual((first_row.sort_order, second_row.sort_order), (1, 2))

    def test_ensure_returns_existing_row_untouched(self):
        row = self.make_row(self.assignment, rate="0.5")
        again = ScheduleRow.ensure(self.schedule, self.assignment)
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(again.rate, Decimal("0.5"))

    def test_saving_a_shift_adds_the_row(self):
        self.make_shift(self.assignment, "8:00", "12:00")
        row = ScheduleRow.objects.get(schedule=self.schedule, assignment=self.assignment)
        self.assertEqual(row.rate, Decimal("0.75"))

    def test_saving_a_second_shift_keeps_the_row_rate(self):
        self.make_shift(self.assignment, "8:00", "12:00")
        ScheduleRow.objects.update(rate=Decimal("0.5"))
        self.make_shift(self.assignment, "8:00", "12:00", day=13)
        self.assertEqual(ScheduleRow.objects.get().rate, Decimal("0.5"))
        self.assertEqual(ScheduleRow.objects.count(), 1)

    def test_shift_limits_take_a_given_rate(self):
        uzd = self.make_assignment(doctor=self.make_doctor("Узи"), specialty=self.uzd, rate="1")
        self.assertEqual(uzd.shift_limits(), (Decimal("5.60"), None))
        self.assertEqual(uzd.shift_limits(rate=Decimal("0.75")), (None, Decimal("5.50")))


class FillRowsMigrationTests(ScheduleTestMixin, TestCase):
    """Данные миграции: строки для уже существующих графиков."""

    def setUp(self):
        self.setUpData()
        self.migration = importlib.import_module("apps.schedule.migrations.0009_fill_schedulerows")

    def run_migration(self):
        self.migration.fill_rows(django_apps, None)

    def test_rows_are_built_from_active_assignments_and_assignments_with_shifts(self):
        schedule = self.make_schedule()
        active = self.make_assignment(doctor=self.make_doctor("Яковлев"))
        also_active = self.make_assignment(doctor=self.make_doctor("Абрамов"), rate="0.5")
        left_with_shift = self.make_assignment(doctor=self.make_doctor("Беляев"), is_active=False)
        left_without_shift = self.make_assignment(doctor=self.make_doctor("Волков"), is_active=False)
        other_department = self.make_assignment(doctor=self.make_doctor("Зайцев"), department=self.dept_b)
        self.make_shift(left_with_shift, "8:00", "12:00")
        ScheduleRow.objects.all().delete()
        self.run_migration()
        rows = list(ScheduleRow.objects.filter(schedule=schedule).order_by("sort_order"))
        self.assertEqual(
            [r.assignment_id for r in rows], [also_active.pk, left_with_shift.pk, active.pk]
        )
        self.assertEqual([r.sort_order for r in rows], [1, 2, 3])
        self.assertEqual(rows[0].rate, Decimal("0.5"))
        used = {r.assignment_id for r in ScheduleRow.objects.all()}
        self.assertNotIn(left_without_shift.pk, used)
        self.assertNotIn(other_department.pk, used)

    def test_running_twice_does_not_duplicate(self):
        self.make_schedule()
        self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.run_migration()
        self.run_migration()
        self.assertEqual(ScheduleRow.objects.count(), 1)

    def test_every_schedule_gets_its_own_rows(self):
        self.make_assignment(doctor=self.make_doctor("Орлов"))
        january = self.make_schedule(month=1)
        february = self.make_schedule(month=2)
        self.run_migration()
        self.assertEqual(ScheduleRow.objects.filter(schedule=january).count(), 1)
        self.assertEqual(ScheduleRow.objects.filter(schedule=february).count(), 1)
        self.assertEqual(Schedule.objects.count(), 2)
        self.assertEqual(Assignment.objects.count(), 1)
