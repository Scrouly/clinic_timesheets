from decimal import Decimal

from django.test import TestCase

from apps.schedule.checks import HOURS_NORM, SHIFT_TOO_LONG, check_schedule
from apps.schedule.models import MonthNorm

from .helpers import ScheduleTestMixin


class RowRateInChecksTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()

    def codes(self):
        return [issue.code for issue in check_schedule(self.schedule)]

    def test_shift_length_rule_uses_the_rate_of_the_row(self):
        assignment = self.make_assignment(specialty=self.uzd, rate="1")  # ставка по умолчанию: не менее 5,6 ч
        self.make_shift(assignment, "8:00", "14:00")  # 6 ч: для полной ставки нормально
        self.assertNotIn(SHIFT_TOO_LONG, self.codes())
        self.make_row(assignment, self.schedule, rate="0.75")  # в этом месяце 0,75: не более 5,5 ч
        self.assertIn(SHIFT_TOO_LONG, self.codes())

    def test_norm_uses_the_rate_of_the_row(self):
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("8"))
        assignment = self.make_assignment(rate="1")
        self.make_shift(assignment, "8:00", "12:00")  # 4 ч
        self.assertIn(HOURS_NORM, self.codes())  # норма 8 ч при ставке 1
        self.make_row(assignment, self.schedule, rate="0.5")  # норма 4 ч
        self.assertNotIn(HOURS_NORM, self.codes())

    def test_row_without_records_has_no_norm_issue(self):
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("8"))
        self.make_row(self.make_assignment())
        self.assertEqual(self.codes(), [])

    def test_row_with_only_absences_still_reports_the_deficit(self):
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("8"))
        assignment = self.make_assignment()
        self.make_shift(assignment, None, None, kind=self.vacation)
        self.assertIn(HOURS_NORM, self.codes())
