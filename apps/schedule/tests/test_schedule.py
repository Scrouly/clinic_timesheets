from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import Department
from apps.schedule.models import Schedule, ScheduleStatus


class ScheduleTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Хирургическое отделение")

    def test_unique_per_department_month(self):
        Schedule.objects.create(department=self.department, year=2026, month=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Schedule.objects.create(department=self.department, year=2026, month=1)

    def test_month_must_be_1_to_12(self):
        for month in (0, 13):
            with self.assertRaises(ValidationError, msg=month):
                Schedule(department=self.department, year=2026, month=month).full_clean()

    def test_default_status_is_draft(self):
        schedule = Schedule.objects.create(department=self.department, year=2026, month=2)
        self.assertEqual(schedule.status, ScheduleStatus.DRAFT)
        self.assertIsNone(schedule.approved_on)
