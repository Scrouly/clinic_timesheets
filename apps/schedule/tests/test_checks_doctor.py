from django.test import TestCase

from apps.schedule.checks import DOCTOR_DOUBLE_BOOKED, check_doctor_overlap

from .helpers import ScheduleTestMixin


class CheckDoctorOverlapTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.doctor = self.make_doctor("Орлов")

    def test_overlap_in_two_departments(self):
        in_a = self.make_assignment(doctor=self.doctor, department=self.dept_a)
        in_b = self.make_assignment(doctor=self.doctor, department=self.dept_b)
        first = self.make_shift(in_a, "9:00", "13:00", cabinet=self.cab1)
        second = self.make_shift(in_b, "12:00", "16:00", cabinet=self.cab2)
        issues = check_doctor_overlap([first, second])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, DOCTOR_DOUBLE_BOOKED)
        self.assertEqual(set(issues[0].shift_ids), {first.id, second.id})

    def test_back_to_back_is_not_overlap(self):
        in_a = self.make_assignment(doctor=self.doctor, department=self.dept_a)
        in_b = self.make_assignment(doctor=self.doctor, department=self.dept_b)
        first = self.make_shift(in_a, "9:00", "13:00")
        second = self.make_shift(in_b, "13:00", "16:00", cabinet=self.cab2)
        self.assertEqual(check_doctor_overlap([first, second]), [])

    def test_different_days_ok(self):
        assignment = self.make_assignment(doctor=self.doctor)
        first = self.make_shift(assignment, "9:00", "13:00", day=12)
        second = self.make_shift(assignment, "9:00", "13:00", day=13)
        self.assertEqual(check_doctor_overlap([first, second]), [])

    def test_same_assignment_overlap_detected(self):
        assignment = self.make_assignment(doctor=self.doctor)
        first = self.make_shift(assignment, "9:00", "13:00", cabinet=self.cab1)
        second = self.make_shift(assignment, "10:00", "14:00", cabinet=self.cab2)
        issues = check_doctor_overlap([first, second])
        self.assertEqual(len(issues), 1)
        self.assertEqual(set(issues[0].shift_ids), {first.id, second.id})

    def test_different_doctors_ok(self):
        first = self.make_shift(self.make_assignment(doctor=self.doctor), "9:00", "13:00")
        second = self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab2)
        self.assertEqual(check_doctor_overlap([first, second]), [])

    def test_non_working_ignored(self):
        assignment = self.make_assignment(doctor=self.doctor)
        work = self.make_shift(assignment, "9:00", "13:00")
        vacation = self.make_shift(assignment, None, None, kind=self.vacation)
        self.assertEqual(check_doctor_overlap([work, vacation]), [])
