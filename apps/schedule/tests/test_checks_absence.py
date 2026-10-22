from django.test import TestCase

from apps.schedule.checks import WORK_ON_ABSENCE, check_work_on_absence

from .helpers import ScheduleTestMixin


class CheckWorkOnAbsenceTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()

    def test_work_and_vacation_same_day(self):
        assignment = self.make_assignment()
        work = self.make_shift(assignment, "9:00", "13:00")
        vacation = self.make_shift(assignment, None, None, kind=self.vacation)
        issues = check_work_on_absence([work, vacation])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, WORK_ON_ABSENCE)
        self.assertEqual(set(issues[0].shift_ids), {work.id, vacation.id})

    def test_vacation_other_assignment_ok(self):
        doctor = self.make_doctor()
        in_a = self.make_assignment(doctor=doctor, department=self.dept_a)
        in_b = self.make_assignment(doctor=doctor, department=self.dept_b)
        work = self.make_shift(in_a, "9:00", "13:00")
        vacation = self.make_shift(in_b, None, None, kind=self.vacation)
        self.assertEqual(check_work_on_absence([work, vacation]), [])

    def test_work_only_ok(self):
        assignment = self.make_assignment()
        work = self.make_shift(assignment, "9:00", "13:00")
        self.assertEqual(check_work_on_absence([work]), [])

    def test_vacation_on_other_day_ok(self):
        assignment = self.make_assignment()
        work = self.make_shift(assignment, "9:00", "13:00", day=12)
        vacation = self.make_shift(assignment, None, None, day=13, kind=self.vacation)
        self.assertEqual(check_work_on_absence([work, vacation]), [])
