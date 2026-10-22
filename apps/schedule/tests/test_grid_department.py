from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Role
from apps.schedule.grids import build_department_grid
from apps.schedule.models import CalendarDay, DayKind, MonthNorm, Schedule
from apps.schedule.norms import deficit_hours, norm_hours, planned_hours

from .helpers import ScheduleTestMixin, make_access_user


class DepartmentGridTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("8"))
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.editor = make_access_user("editor", edit=[self.dept_a])

    def grid(self, user=None):
        return build_department_grid(self.schedule, user or self.editor)

    def cell(self, grid, row=0, day=12):
        return grid["rows"][row]["cells"][day - 1]

    def test_days_use_calendar_and_weekdays(self):
        CalendarDay.objects.create(date=date(2026, 1, 1), kind=DayKind.HOLIDAY)
        CalendarDay.objects.create(date=date(2026, 1, 10), kind=DayKind.WORKDAY)  # рабочая суббота
        days = self.grid()["days"]
        self.assertEqual(len(days), 31)
        self.assertTrue(days[0]["is_weekend"])  # праздник
        self.assertTrue(days[2]["is_weekend"])  # суббота 3 января
        self.assertFalse(days[9]["is_weekend"])  # суббота 10 января, но рабочий день
        self.assertFalse(days[11]["is_weekend"])  # понедельник 12 января
        self.assertEqual(days[11]["weekday"], "пн")

    def test_rows_are_assignments_of_department(self):
        first = self.make_assignment(doctor=self.make_doctor("Анохин"))
        second = self.make_assignment(doctor=self.make_doctor("Борисов"))
        self.make_assignment(doctor=self.make_doctor("Власов"), department=self.dept_b)
        self.make_assignment(doctor=self.make_doctor("Громов"), is_active=False)  # без смен, скрыт
        busy_inactive = self.make_assignment(doctor=self.make_doctor("Дроздов"), is_active=False)
        self.make_shift(busy_inactive, "9:00", "13:00")  # со сменами, показывается
        rows = [row["assignment"] for row in self.grid()["rows"]]
        self.assertEqual(rows, [first, second, busy_inactive])

    def test_cell_text_for_working_and_absence(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "8:00", "14:40", day=12)
        self.make_shift(assignment, None, None, day=13, kind=self.vacation)
        grid = self.grid()
        shift_cell, absence_cell, off_cell = (self.cell(grid, day=d) for d in (12, 13, 14))
        self.assertEqual(shift_cell["kind"], "shift")
        self.assertEqual(shift_cell["items"][0]["label"], "08:00–14:40")
        self.assertEqual(shift_cell["items"][0]["cabinet"], "301")
        self.assertEqual(absence_cell["kind"], "absence")
        self.assertEqual(absence_cell["items"][0]["label"], "ОТП")
        self.assertEqual(off_cell["kind"], "off")
        self.assertEqual(off_cell["items"], [])

    def test_two_shifts_in_one_day_in_one_cell(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "8:00", "12:00", cabinet=self.cab1)
        self.make_shift(assignment, "13:00", "17:00", cabinet=self.cab2)
        items = self.cell(self.grid())["items"]
        self.assertEqual([i["label"] for i in items], ["08:00–12:00", "13:00–17:00"])

    def test_editable_follows_edit_access(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "8:00", "12:00")
        cases = (
            (self.editor, True),
            (make_access_user("looker", view=[self.dept_a]), False),
            (make_access_user("boss", role=Role.HR), True),
            (make_access_user("see", role=Role.VIEWER), False),
        )
        for user, expected in cases:
            grid = self.grid(user)
            self.assertEqual(grid["can_edit"], expected, user.username)
            self.assertEqual(self.cell(grid)["editable"], expected, user.username)
            self.assertEqual(self.cell(grid)["items"][0]["editable"], expected, user.username)

    def test_issue_cells_marked(self):
        mine = self.make_assignment()
        clash = self.make_shift(mine, "9:00", "13:00", day=12, cabinet=self.cab1)
        self.make_shift(self.make_assignment(department=self.dept_b), "12:00", "16:00", day=12, cabinet=self.cab1)
        self.make_shift(mine, "9:00", "17:00", day=13, cabinet=self.cab2)  # без ошибок: 8 ч при норме 8 ч
        grid = self.grid()
        self.assertTrue(self.cell(grid, day=12)["has_issue"])
        self.assertFalse(self.cell(grid, day=13)["has_issue"])
        self.assertIn(clash.id, [i["id"] for i in self.cell(grid, day=12)["items"]])

    def test_totals(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "17:00", day=12)
        self.make_shift(assignment, "9:00", "13:00", day=13)
        self.make_shift(assignment, None, None, day=14, kind=self.vacation)
        row = self.grid()["rows"][0]
        self.assertEqual(row["planned"], planned_hours(assignment, 2026, 1))
        self.assertEqual(row["norm"], norm_hours(assignment, 2026, 1))
        self.assertEqual(row["deficit"], deficit_hours(assignment, 2026, 1))
        self.assertEqual(row["worked_days"], 2)
        self.assertEqual(row["deficit"], Decimal("-4.00"))
        self.assertEqual(row["deviation"], Decimal("4.00"))
        self.assertTrue(row["has_norm_issue"])

    def test_no_norm_gives_empty_totals(self):
        MonthNorm.objects.all().delete()
        assignment = self.make_assignment()
        self.make_shift(assignment, "9:00", "13:00")
        row = self.grid()["rows"][0]
        self.assertIsNone(row["norm"])
        self.assertIsNone(row["deficit"])
        self.assertFalse(row["has_norm_issue"])
