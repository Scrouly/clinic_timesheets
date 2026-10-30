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

    def test_rows_are_the_schedule_rows_in_their_order(self):
        first = self.make_assignment(doctor=self.make_doctor("Анохин"))
        second = self.make_assignment(doctor=self.make_doctor("Борисов"))
        self.make_assignment(doctor=self.make_doctor("Власов"), department=self.dept_b)
        self.make_assignment(doctor=self.make_doctor("Громов"))  # есть в отделении, но не в этом графике
        busy_inactive = self.make_assignment(doctor=self.make_doctor("Дроздов"), is_active=False)
        self.make_row(second)
        self.make_row(first)
        self.make_shift(busy_inactive, "9:00", "13:00")  # смена сама добавляет строку
        rows = [row["assignment"] for row in self.grid()["rows"]]
        self.assertEqual(rows, [second, first, busy_inactive])

    def test_row_rate_is_shown_and_used_for_the_norm(self):
        assignment = self.make_assignment(rate="1")
        self.make_row(assignment, rate="0.5")
        row = self.grid()["rows"][0]
        self.assertIn("0,5 ст.", row["position"])
        self.assertEqual(row["norm"], Decimal("4.00"))

    def test_row_exposes_its_object_and_shift_count(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, "8:00", "12:00", day=12)
        self.make_shift(assignment, "8:00", "12:00", day=13)
        row = self.grid()["rows"][0]
        self.assertEqual(row["shift_count"], 2)
        self.assertEqual(row["row"].assignment_id, assignment.pk)

    def test_assignment_without_a_row_is_not_shown(self):
        self.make_assignment()
        self.assertEqual(self.grid()["rows"], [])

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


class ItemHoursTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.editor = make_access_user("editor", edit=[self.dept_a])
        self.assignment = self.make_assignment()

    def items(self, day):
        grid = build_department_grid(self.schedule, self.editor)
        return grid["rows"][0]["cells"][day - 1]["items"]

    def test_item_has_hours_for_working_shift_only(self):
        self.make_shift(self.assignment, "8:00", "14:40", day=12)
        self.make_shift(self.assignment, None, None, day=13, kind=self.vacation)
        (work,) = self.items(12)
        (absence,) = self.items(13)
        self.assertEqual(work["hours"], Decimal("6.67"))
        self.assertIsNone(absence["hours"])

    def test_item_title_explains_hours_and_cabinet(self):
        self.make_shift(self.assignment, "9:00", "15:00", day=12)
        self.make_shift(self.assignment, None, None, day=13, kind=self.vacation)
        self.assertEqual(self.items(12)[0]["title"], "6 ч, кабинет 301")
        self.assertEqual(self.items(13)[0]["title"], "Отпуск")

    def test_existing_item_keys_are_unchanged(self):
        self.make_shift(self.assignment, "9:00", "15:00", day=12)
        item = self.items(12)[0]
        self.assertEqual(
            (item["label"], item["cabinet"], item["working"], item["editable"]), ("09:00–15:00", "301", True, True)
        )
        self.assertIn("id", item)
