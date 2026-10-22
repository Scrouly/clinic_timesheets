from decimal import Decimal

from django.test import TestCase

from apps.schedule.checks import HOURS_NORM, check_hours_norm, check_schedule
from apps.schedule.models import MonthNorm, Schedule, SpecialtyMonthNorm
from apps.schedule.norms import deficit_hours, norm_hours, planned_hours

from .helpers import ScheduleTestMixin


class NormsTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("145.3"))

    def test_norm_by_rate(self):
        expected = {
            "1": "145.30",
            "0.75": "108.98",
            "0.5": "72.65",
            "0.25": "36.33",
            "1.25": "181.63",
        }
        for rate, norm in expected.items():
            assignment = self.make_assignment(rate=rate)
            self.assertEqual(norm_hours(assignment, 2026, 1), Decimal(norm), rate)

    def test_specialty_norm_overrides_general(self):
        SpecialtyMonthNorm.objects.create(specialty=self.uzd, year=2026, month=1, hours=Decimal("132"))
        uzd = self.make_assignment(specialty=self.uzd, rate="1")
        surgeon = self.make_assignment(specialty=self.surgeon, rate="1")
        self.assertEqual(norm_hours(uzd, 2026, 1), Decimal("132.00"))
        self.assertEqual(norm_hours(surgeon, 2026, 1), Decimal("145.30"))

    def test_no_norm_returns_none(self):
        assignment = self.make_assignment()
        self.assertIsNone(norm_hours(assignment, 2026, 2))
        self.assertIsNone(deficit_hours(assignment, 2026, 2))

    def test_planned_counts_only_working_shifts(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "13:00", day=12)
        self.make_shift(assignment, None, None, day=13, kind=self.vacation)
        self.assertEqual(planned_hours(assignment, 2026, 1), Decimal("4.00"))
        self.assertEqual(planned_hours(assignment, 2026, 2), Decimal("0.00"))

    def test_deficit(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "13:00")
        self.assertEqual(deficit_hours(assignment, 2026, 1), Decimal("141.30"))


class CheckHoursNormTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("8"))

    def schedule_of(self, department):
        return Schedule.objects.get(department=department, year=2026, month=1)

    def test_issue_when_not_equal(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "13:00")  # 4 ч при норме 8 ч
        issues = check_hours_norm(self.schedule_of(self.dept_a))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, HOURS_NORM)
        self.assertEqual(issues[0].assignment_id, assignment.id)
        self.assertEqual(issues[0].shift_ids, ())

    def test_no_issue_when_equal(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "17:00")  # ровно 8 ч
        self.assertEqual(check_hours_norm(self.schedule_of(self.dept_a)), [])

    def test_skips_assignment_without_shifts(self):
        self.make_assignment()  # без смен, пропускается
        busy = self.make_assignment()
        self.make_shift(busy, "9:00", "17:00")
        self.assertEqual(check_hours_norm(self.schedule_of(self.dept_a)), [])

    def test_skips_assignment_without_norm(self):
        MonthNorm.objects.all().delete()
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "13:00")
        self.assertEqual(check_hours_norm(self.schedule_of(self.dept_a)), [])

    def test_check_schedule_includes_hours_norm(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "13:00")
        issues = check_schedule(self.schedule_of(self.dept_a))
        self.assertEqual([(i.code, i.assignment_id) for i in issues], [(HOURS_NORM, assignment.id)])
