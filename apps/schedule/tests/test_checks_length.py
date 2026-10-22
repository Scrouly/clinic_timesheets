from decimal import Decimal

from django.test import TestCase

from apps.schedule.checks import SHIFT_TOO_LONG, SHIFT_TOO_SHORT, Issue, check_shift_length

from .helpers import ScheduleTestMixin


class CheckShiftLengthTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()

    def test_too_long_for_part_rate(self):
        assignment = self.make_assignment(specialty=self.uzd, rate="0.75")
        long = self.make_shift(assignment, "9:00", "15:00")
        ok = self.make_shift(assignment, "9:00", "14:00", day=13)
        issues = check_shift_length([long, ok])
        self.assertEqual(len(issues), 1)
        self.assertIsInstance(issues[0], Issue)
        self.assertEqual(issues[0].code, SHIFT_TOO_LONG)
        self.assertEqual(issues[0].shift_ids, (long.id,))

    def test_too_short_for_full_rate(self):
        assignment = self.make_assignment(specialty=self.uzd, rate="1")
        short = self.make_shift(assignment, "9:00", "14:30")  # 5,5 ч
        boundary = self.make_shift(assignment, "9:00", "14:36", day=13)  # ровно 5,6 ч
        issues = check_shift_length([short, boundary])
        self.assertEqual([(i.code, i.shift_ids) for i in issues], [(SHIFT_TOO_SHORT, (short.id,))])

    def test_no_rule_no_issue(self):
        assignment = self.make_assignment(specialty=self.surgeon, rate="0.25")
        shifts = [
            self.make_shift(assignment, "9:00", "9:30"),
            self.make_shift(assignment, "0:30", "23:30", day=13),
        ]
        self.assertEqual(check_shift_length(shifts), [])

    def test_own_limits_override_rule(self):
        assignment = self.make_assignment(
            specialty=self.uzd, rate="0.75", min_shift_hours=Decimal("4"), max_shift_hours=Decimal("6")
        )
        shift = self.make_shift(assignment, "9:00", "15:00")  # 6 ч, по правилу профессии было бы много
        self.assertEqual(check_shift_length([shift]), [])

    def test_non_working_shifts_ignored(self):
        assignment = self.make_assignment(specialty=self.uzd, rate="0.75")
        vacation = self.make_shift(assignment, None, None, kind=self.vacation)
        self.assertEqual(check_shift_length([vacation]), [])
