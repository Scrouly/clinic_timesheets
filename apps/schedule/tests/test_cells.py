from datetime import date, time

from django.test import TestCase

from apps.schedule.cells import CellConflict, CellRejected, apply_cell, default_cabinet_for
from apps.schedule.models import Shift

from .helpers import ScheduleTestMixin, t

DAY = date(2026, 1, 12)


class ApplyCellBase(ScheduleTestMixin):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.assignment = self.make_assignment()
        self.row = self.make_row(self.assignment)

    def apply(self, raw, expected=None, day=DAY):
        return apply_cell(self.schedule, self.row, day, raw, expected)

    def shifts(self, day=DAY):
        return list(Shift.objects.filter(schedule=self.schedule, assignment=self.assignment, date=day))


class ApplyCellTests(ApplyCellBase, TestCase):
    def test_creates_a_shift(self):
        self.assertEqual(self.apply("9-15 301"), "09:00–15:00 · 301")
        shift = self.shifts()[0]
        actual = (shift.kind, shift.start, shift.end, shift.cabinet)
        self.assertEqual(actual, (self.work, t("9:00"), t("15:00"), self.cab1))

    def test_replaces_a_shift_and_keeps_its_id(self):
        old = self.make_shift(self.assignment, "8:00", "13:00", day=12)
        self.apply("9-15 302")
        self.assertEqual([s.id for s in self.shifts()], [old.id])
        old.refresh_from_db()
        self.assertEqual((old.start, old.end, old.cabinet), (time(9), time(15), self.cab2))

    def test_unchanged_shift_is_not_touched(self):
        old = self.make_shift(self.assignment, "8:00", "13:00", day=12)
        self.apply("8-13 301; 14-18 302")
        ids = {s.id for s in self.shifts()}
        self.assertEqual(len(ids), 2)
        self.assertIn(old.id, ids)

    def test_two_shifts(self):
        self.assertEqual(self.apply("8-12 301; 14-18 302"), "08:00–12:00 · 301; 14:00–18:00 · 302")
        self.assertEqual(len(self.shifts()), 2)

    def test_extra_shifts_are_deleted(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=12)
        self.make_shift(self.assignment, "14:00", "18:00", day=12, cabinet=self.cab2)
        self.apply("9-11 301")
        self.assertEqual(len(self.shifts()), 1)

    def test_empty_text_clears_the_day(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=12)
        self.assertEqual(self.apply(""), "")
        self.assertEqual(self.shifts(), [])

    def test_absence_replaces_work(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=12)
        self.assertEqual(self.apply("отп"), "ОТП")
        shift = self.shifts()[0]
        self.assertEqual((shift.kind, shift.start, shift.end, shift.cabinet), (self.vacation, None, None, None))

    def test_other_days_and_doctors_are_untouched(self):
        other = self.make_assignment()
        self.make_row(other)
        mine_other_day = self.make_shift(self.assignment, "8:00", "12:00", day=13)
        theirs = self.make_shift(other, "8:00", "12:00", day=12)
        self.apply("9-15 301")
        self.assertTrue(Shift.objects.filter(pk=mine_other_day.pk).exists())
        self.assertTrue(Shift.objects.filter(pk=theirs.pk).exists())

    def test_date_outside_the_month_is_rejected(self):
        with self.assertRaises(CellRejected):
            self.apply("9-15 301", day=date(2026, 2, 3))
        self.assertEqual(Shift.objects.count(), 0)


class DefaultCabinetTests(ApplyCellBase, TestCase):
    def test_cabinet_of_the_last_shift_of_the_row(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=5, cabinet=self.cab1)
        self.make_shift(self.assignment, "8:00", "12:00", day=9, cabinet=self.cab2)
        self.assertEqual(self.apply("9-15"), "09:00–15:00 · 302")

    def test_most_frequent_cabinet_of_the_doctor_when_the_row_has_no_shifts(self):
        february = self.make_schedule(month=2)
        self.make_row(self.assignment, february)
        for day in (2, 3, 4):
            Shift.objects.create(
                schedule=february, assignment=self.assignment, date=date(2026, 2, day), kind=self.work,
                start=t("8:00"), end=t("12:00"), cabinet=self.cab2,
            )
        Shift.objects.create(
            schedule=february, assignment=self.assignment, date=date(2026, 2, 5), kind=self.work,
            start=t("8:00"), end=t("12:00"), cabinet=self.cab1,
        )
        self.assertEqual(default_cabinet_for(self.schedule, self.assignment), self.cab2)

    def test_no_history_means_the_cabinet_must_be_typed(self):
        with self.assertRaises(CellRejected) as caught:
            self.apply("9-15")
        self.assertIn("Укажите кабинет", str(caught.exception))
        self.assertEqual(self.shifts(), [])


class RejectionTests(ApplyCellBase, TestCase):
    def test_bad_text_changes_nothing(self):
        old = self.make_shift(self.assignment, "8:00", "12:00", day=12)
        with self.assertRaises(CellRejected) as caught:
            self.apply("8-")
        self.assertIn("Не понял", str(caught.exception))
        self.assertEqual([s.id for s in self.shifts()], [old.id])

    def test_failure_in_the_second_part_rolls_back_the_first(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=12)
        with self.assertRaises(CellRejected):
            self.apply("9-11 301; 14-")
        shift = self.shifts()[0]
        self.assertEqual((shift.start, shift.end), (time(8), time(12)))


class ConflictTests(ApplyCellBase, TestCase):
    def test_matching_expected_is_accepted(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=12)
        self.assertEqual(self.apply("9-15 301", expected="08:00–12:00 · 301"), "09:00–15:00 · 301")

    def test_changed_cell_gives_a_conflict_and_is_not_written(self):
        self.make_shift(self.assignment, "8:00", "14:00", day=12)
        with self.assertRaises(CellConflict) as caught:
            self.apply("9-15 301", expected="08:00–12:00 · 301")
        self.assertEqual(caught.exception.current, "08:00–14:00 · 301")
        self.assertEqual(self.shifts()[0].end, time(14))

    def test_empty_expected_means_the_cell_was_empty(self):
        self.make_shift(self.assignment, "8:00", "14:00", day=12)
        with self.assertRaises(CellConflict):
            self.apply("9-15 301", expected="")
        self.assertEqual(self.apply("9-15 301", expected="08:00–14:00 · 301"), "09:00–15:00 · 301")

    def test_without_expected_the_comparison_is_skipped(self):
        self.make_shift(self.assignment, "8:00", "14:00", day=12)
        self.assertEqual(self.apply("9-15 301"), "09:00–15:00 · 301")
