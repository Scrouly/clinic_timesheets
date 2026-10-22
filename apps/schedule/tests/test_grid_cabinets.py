from decimal import Decimal

from django.test import TestCase

from apps.schedule.grids import build_cabinet_grid
from apps.schedule.models import Cabinet

from .helpers import ScheduleTestMixin, make_access_user


class CabinetGridTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.editor = make_access_user("editor", edit=[self.dept_a], view=[self.dept_b])

    def grid(self, user=None):
        return build_cabinet_grid(2026, 1, user or self.editor)

    def entry(self, grid, cabinet):
        return next(e for e in grid["cabinets"] if e["cabinet"] == cabinet)

    def test_only_flagged_active_cabinets(self):
        self.cab2.in_cabinet_schedule = False
        self.cab2.save()
        Cabinet.objects.create(name="303", is_active=False)
        self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab1)
        self.make_shift(self.make_assignment(), "9:00", "13:00", cabinet=self.cab2)
        self.assertEqual([e["cabinet"] for e in self.grid()["cabinets"]], [self.cab1])

    def test_shifts_from_any_department_included(self):
        self.make_shift(self.make_assignment(department=self.dept_a), "9:00", "13:00", cabinet=self.cab1)
        self.make_shift(self.make_assignment(department=self.dept_b), "14:00", "18:00", cabinet=self.cab1)
        self.assertEqual(len(self.entry(self.grid(), self.cab1)["doctors"]), 2)

    def test_doctors_come_from_shifts_sorted_by_name(self):
        self.make_shift(self.make_assignment(doctor=self.make_doctor("Яковлев")), "9:00", "13:00")
        self.make_shift(self.make_assignment(doctor=self.make_doctor("Абрамов")), "14:00", "18:00")
        names = [d["doctor"].last_name for d in self.entry(self.grid(), self.cab1)["doctors"]]
        self.assertEqual(names, ["Абрамов", "Яковлев"])

    def test_cabinet_without_shifts_is_empty_column(self):
        entry = self.entry(self.grid(), self.cab1)
        self.assertEqual(entry["doctors"], [])
        self.assertEqual(entry["total"], Decimal("0"))
        self.assertEqual(self.grid()["day_rows"][0]["groups"][0]["cells"], [])

    def test_cabinets_ordered_by_sort_order(self):
        self.cab1.sort_order = 5
        self.cab1.save()
        self.cab2.sort_order = 1
        self.cab2.save()
        self.assertEqual([e["cabinet"] for e in self.grid()["cabinets"]], [self.cab2, self.cab1])

    def test_foreign_department_shift_not_editable(self):
        self.make_shift(self.make_assignment(department=self.dept_a), "9:00", "13:00", cabinet=self.cab1, day=12)
        self.make_shift(self.make_assignment(department=self.dept_b), "9:00", "13:00", cabinet=self.cab1, day=13)
        by_name = {}
        for doctor_entry in self.entry(self.grid(), self.cab1)["doctors"]:
            for cell in doctor_entry["cells"]:
                for item in cell["items"]:
                    by_name[doctor_entry["doctor"].pk] = item["editable"]
        self.assertEqual(sorted(by_name.values()), [False, True])

    def test_totals(self):
        first = self.make_assignment()
        second = self.make_assignment()
        self.make_shift(first, "9:00", "13:00", day=12, cabinet=self.cab1)  # 4 ч
        self.make_shift(first, "9:00", "11:00", day=13, cabinet=self.cab1)  # 2 ч
        self.make_shift(second, "14:00", "17:00", day=12, cabinet=self.cab1)  # 3 ч
        grid = self.grid()
        entry = self.entry(grid, self.cab1)
        self.assertEqual(sorted(d["total"] for d in entry["doctors"]), [Decimal("3"), Decimal("6")])
        self.assertEqual(entry["total"], Decimal("9"))
        self.assertEqual(entry["day_totals"][11], Decimal("7"))  # 12 января
        self.assertEqual(grid["day_rows"][11]["groups"][0]["total"], Decimal("7"))

    def test_non_working_kinds_are_not_shown(self):
        assignment = self.make_assignment()
        self.make_shift(assignment, None, None, kind=self.vacation)
        self.assertEqual(self.entry(self.grid(), self.cab1)["doctors"], [])

    def test_toggle_flag_changes_membership(self):
        self.assertIn(self.cab1, [e["cabinet"] for e in self.grid()["cabinets"]])
        self.cab1.in_cabinet_schedule = False
        self.cab1.save()
        self.assertNotIn(self.cab1, [e["cabinet"] for e in self.grid()["cabinets"]])

    def test_clash_cells_marked(self):
        self.make_shift(self.make_assignment(department=self.dept_a), "9:00", "13:00", cabinet=self.cab1)
        self.make_shift(self.make_assignment(department=self.dept_b), "12:00", "16:00", cabinet=self.cab1)
        entry = self.entry(self.grid(), self.cab1)
        marked = [c["has_issue"] for d in entry["doctors"] for c in d["cells"] if c["items"]]
        self.assertEqual(marked, [True, True])

    def test_days_and_flags(self):
        grid = self.grid()
        self.assertEqual((grid["year"], grid["month"]), (2026, 1))
        self.assertEqual(len(grid["days"]), 31)
        self.assertEqual(len(grid["day_rows"]), 31)
        self.assertTrue(grid["can_edit"])
        self.assertFalse(self.grid(make_access_user("looker", view=[self.dept_a]))["can_edit"])
