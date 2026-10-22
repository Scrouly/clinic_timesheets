from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import Department
from apps.schedule.checks import CABINET_OVERLAP, check_schedule
from apps.schedule.models import Cabinet, MonthNorm, Schedule, Shift, Specialty, TimeKind


class SeedDemoScheduleTests(TestCase):
    def seed(self):
        call_command("seed_demo", force=True, verbosity=0)

    def test_seed_creates_demo_schedule_data(self):
        self.seed()
        today = timezone.localdate()
        self.assertTrue(TimeKind.objects.filter(is_working=True).exists())
        self.assertTrue(TimeKind.objects.filter(is_working=False).exists())
        self.assertTrue(Cabinet.objects.filter(name="117").exists())
        self.assertTrue(Specialty.objects.filter(length_rules__isnull=False).exists())
        self.assertTrue(MonthNorm.objects.filter(year=today.year, month=today.month).exists())
        self.assertTrue(Schedule.objects.filter(year=today.year, month=today.month).exists())
        self.assertTrue(Shift.objects.filter(kind__is_working=True).exists())
        self.assertTrue(Shift.objects.filter(kind__is_working=False).exists())

    def test_demo_contains_a_cabinet_clash_to_show_errors(self):
        self.seed()
        today = timezone.localdate()
        schedule = Schedule.objects.get(
            department=Department.objects.get(name="Консультативное отделение №2"),
            year=today.year,
            month=today.month,
        )
        self.assertIn(CABINET_OVERLAP, [issue.code for issue in check_schedule(schedule)])

    def test_seed_is_idempotent(self):
        self.seed()
        counts = (Shift.objects.count(), Schedule.objects.count(), Cabinet.objects.count())
        self.seed()
        self.assertEqual(
            (Shift.objects.count(), Schedule.objects.count(), Cabinet.objects.count()), counts
        )

    def test_seed_refuses_without_debug(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                call_command("seed_demo", verbosity=0)
        self.assertEqual(Shift.objects.count(), 0)
