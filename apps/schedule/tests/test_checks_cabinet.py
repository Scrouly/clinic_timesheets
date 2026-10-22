from django.test import TestCase

from apps.schedule.checks import (
    CABINET_OVERLAP,
    SHIFT_TOO_LONG,
    WORK_ON_ABSENCE,
    check_cabinet_overlap,
    check_schedule,
)
from apps.schedule.models import Cabinet, Schedule

from .helpers import ScheduleTestMixin


class CheckCabinetOverlapTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()

    def test_overlap_in_regular_cabinet(self):
        first = self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab1)
        second = self.make_shift(self.make_assignment(), "12:00", "16:00", cabinet=self.cab1)
        issues = check_cabinet_overlap([first, second])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, CABINET_OVERLAP)
        self.assertEqual(set(issues[0].shift_ids), {first.id, second.id})

    def test_shared_cabinet_not_flagged(self):
        shared = Cabinet.objects.create(name="Операционная", is_shared=True)
        first = self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=shared)
        second = self.make_shift(self.make_assignment(), "12:00", "16:00", cabinet=shared)
        self.assertEqual(check_cabinet_overlap([first, second]), [])

    def test_back_to_back_is_not_overlap(self):
        first = self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab1)
        second = self.make_shift(self.make_assignment(), "13:00", "16:00", cabinet=self.cab1)
        self.assertEqual(check_cabinet_overlap([first, second]), [])

    def test_same_doctor_same_cabinet_not_cabinet_issue(self):
        assignment = self.make_assignment()
        first = self.make_shift(assignment, "9:00", "13:00", cabinet=self.cab1)
        second = self.make_shift(assignment, "12:00", "16:00", cabinet=self.cab1)
        self.assertEqual(check_cabinet_overlap([first, second]), [])

    def test_different_cabinets_ok(self):
        first = self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab1)
        second = self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab2)
        self.assertEqual(check_cabinet_overlap([first, second]), [])


class CheckScheduleTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()

    def test_check_schedule_sees_other_department_clash(self):
        first = self.make_shift(
            self.make_assignment(department=self.dept_a), "9:00", "13:00", cabinet=self.cab1
        )
        second = self.make_shift(
            self.make_assignment(department=self.dept_b), "12:00", "16:00", cabinet=self.cab1
        )
        for department in (self.dept_a, self.dept_b):
            schedule = Schedule.objects.get(department=department, year=2026, month=1)
            issues = check_schedule(schedule)
            self.assertEqual([i.code for i in issues], [CABINET_OVERLAP], department)
            self.assertEqual(set(issues[0].shift_ids), {first.id, second.id})

    def test_check_schedule_skips_unrelated_issues(self):
        dept_c = self.dept_b.__class__.objects.create(name="Отделение В")
        self.make_shift(
            self.make_assignment(department=self.dept_a), "8:00", "9:00", cabinet=self.cab1
        )
        # накладка двух чужих графиков в том же кабинете, мои смены в ней не участвуют
        self.make_shift(self.make_assignment(department=self.dept_b), "12:00", "16:00", cabinet=self.cab1)
        self.make_shift(self.make_assignment(department=dept_c), "13:00", "15:00", cabinet=self.cab1)
        schedule = Schedule.objects.get(department=self.dept_a, year=2026, month=1)
        self.assertEqual(check_schedule(schedule), [])

    def test_check_schedule_collects_length_and_absence_issues(self):
        assignment = self.make_assignment(specialty=self.uzd, rate="0.75")
        self.make_shift(assignment, "9:00", "15:00", day=12)
        self.make_shift(assignment, "9:00", "10:00", day=13)
        self.make_shift(assignment, None, None, day=13, kind=self.vacation)
        schedule = Schedule.objects.get(department=self.dept_a, year=2026, month=1)
        codes = sorted(i.code for i in check_schedule(schedule))
        self.assertEqual(codes, sorted([SHIFT_TOO_LONG, WORK_ON_ABSENCE]))

    def test_clean_schedule_has_no_issues(self):
        self.make_shift(self.make_assignment(), "9:00", "13:00")
        schedule = Schedule.objects.get(department=self.dept_a, year=2026, month=1)
        self.assertEqual(check_schedule(schedule), [])
