from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from apps.schedule import rows
from apps.schedule.models import Assignment, Shift

from .helpers import ScheduleTestMixin


class RowServiceBase(ScheduleTestMixin):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.a = self.make_row(self.make_assignment(doctor=self.make_doctor("Абрамов")))
        self.b = self.make_row(self.make_assignment(doctor=self.make_doctor("Беляев")))
        self.c = self.make_row(self.make_assignment(doctor=self.make_doctor("Волков")))

    def order(self, schedule=None):
        schedule = schedule or self.schedule
        return [r.assignment.doctor.last_name for r in schedule.rows.order_by("sort_order")]


class AddRowTests(RowServiceBase, TestCase):
    def test_new_assignment_is_created_from_doctor_and_specialty(self):
        doctor = self.make_doctor("Герасимов")
        row = rows.add_row(self.schedule, doctor, self.uzd, Decimal("0.75"))
        assignment = Assignment.objects.get(doctor=doctor)
        self.assertEqual((assignment.department_id, assignment.specialty_id), (self.dept_a.pk, self.uzd.pk))
        self.assertEqual(row.rate, Decimal("0.75"))
        self.assertEqual(assignment.rate, Decimal("0.75"))

    def test_existing_assignment_is_reused_and_its_rate_not_changed(self):
        assignment = self.make_assignment(doctor=self.make_doctor("Герасимов"), specialty=self.uzd, rate="1")
        row = rows.add_row(self.schedule, assignment.doctor, self.uzd, Decimal("0.5"))
        self.assertEqual(row.assignment_id, assignment.pk)
        self.assertEqual(Assignment.objects.filter(doctor=assignment.doctor).count(), 1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.rate, Decimal("1.00"))
        self.assertEqual(row.rate, Decimal("0.5"))

    def test_inactive_assignment_is_reactivated(self):
        assignment = self.make_assignment(doctor=self.make_doctor("Герасимов"), is_active=False)
        rows.add_row(self.schedule, assignment.doctor, self.surgeon, Decimal("1"))
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)

    def test_appends_by_default(self):
        rows.add_row(self.schedule, self.make_doctor("Герасимов"), self.surgeon, Decimal("1"))
        self.assertEqual(self.order(), ["Абрамов", "Беляев", "Волков", "Герасимов"])

    def test_inserts_at_position_and_renumbers(self):
        rows.add_row(self.schedule, self.make_doctor("Герасимов"), self.surgeon, Decimal("1"), position=1)
        self.assertEqual(self.order(), ["Абрамов", "Герасимов", "Беляев", "Волков"])
        self.assertEqual([r.sort_order for r in self.schedule.rows.order_by("sort_order")], [1, 2, 3, 4])

    def test_position_is_clamped(self):
        rows.add_row(self.schedule, self.make_doctor("Герасимов"), self.surgeon, Decimal("1"), position=-5)
        rows.add_row(self.schedule, self.make_doctor("Дмитриев"), self.surgeon, Decimal("1"), position=99)
        self.assertEqual(self.order()[0], "Герасимов")
        self.assertEqual(self.order()[-1], "Дмитриев")

    def test_same_doctor_and_specialty_twice_is_refused(self):
        with self.assertRaises(rows.RowExists) as caught:
            rows.add_row(self.schedule, self.a.assignment.doctor, self.surgeon, Decimal("1"))
        self.assertEqual(caught.exception.row, self.a)

    def test_same_doctor_with_another_specialty_is_a_second_row(self):
        row = rows.add_row(self.schedule, self.a.assignment.doctor, self.uzd, Decimal("0.5"))
        self.assertNotEqual(row.assignment_id, self.a.assignment_id)
        self.assertEqual(self.schedule.rows.count(), 4)

    def test_rate_outside_the_allowed_range_is_refused(self):
        for bad in (Decimal("0"), Decimal("-1"), Decimal("2.5")):
            with self.assertRaises(rows.RowError):
                rows.add_row(self.schedule, self.make_doctor(), self.surgeon, bad)


class RemoveRowTests(RowServiceBase, TestCase):
    def test_empty_row_is_removed_without_confirmation(self):
        self.assertEqual(rows.remove_row(self.b), 0)
        self.assertEqual(self.order(), ["Абрамов", "Волков"])
        self.assertEqual([r.sort_order for r in self.schedule.rows.order_by("sort_order")], [1, 2])

    def test_row_with_shifts_needs_the_exact_count(self):
        self.make_shift(self.b.assignment, "8:00", "12:00", day=12)
        self.make_shift(self.b.assignment, "8:00", "12:00", day=13)
        with self.assertRaises(rows.ConfirmRequired) as caught:
            rows.remove_row(self.b)
        self.assertEqual(caught.exception.shifts, 2)
        with self.assertRaises(rows.ConfirmRequired):
            rows.remove_row(self.b, confirm=1)
        self.assertEqual(self.schedule.rows.count(), 3)

    def test_confirmed_removal_deletes_the_month_shifts_only(self):
        self.make_shift(self.b.assignment, "8:00", "12:00", day=12)
        february = self.make_schedule(month=2)
        other_month = Shift.objects.create(
            schedule=february,
            assignment=self.b.assignment,
            date=date(2026, 2, 3),
            kind=self.work,
            start=time(8),
            end=time(12),
            cabinet=self.cab1,
        )
        self.assertEqual(rows.remove_row(self.b, confirm=1), 1)
        self.assertFalse(Shift.objects.filter(schedule=self.schedule, assignment=self.b.assignment).exists())
        self.assertTrue(Shift.objects.filter(pk=other_month.pk).exists())
        self.assertTrue(Assignment.objects.filter(pk=self.b.assignment_id).exists())


class MoveRowTests(RowServiceBase, TestCase):
    def test_move_down_and_up(self):
        rows.move_row(self.a, direction="down")
        self.assertEqual(self.order(), ["Беляев", "Абрамов", "Волков"])
        rows.move_row(self.a, direction="up")
        self.assertEqual(self.order(), ["Абрамов", "Беляев", "Волков"])

    def test_moving_past_the_ends_changes_nothing(self):
        rows.move_row(self.a, direction="up")
        rows.move_row(self.c, direction="down")
        self.assertEqual(self.order(), ["Абрамов", "Беляев", "Волков"])

    def test_move_to_position(self):
        rows.move_row(self.c, position=0)
        self.assertEqual(self.order(), ["Волков", "Абрамов", "Беляев"])


class UpdateRowTests(RowServiceBase, TestCase):
    def test_rate_changes_only_this_row(self):
        rows.update_row(self.a, rate=Decimal("0.5"))
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.rate, Decimal("0.5"))
        self.assertEqual(self.b.rate, Decimal("1.00"))
        self.assertEqual(self.a.assignment.rate, Decimal("1.00"))

    def test_specialty_change_moves_shifts_to_the_other_assignment(self):
        shift = self.make_shift(self.a.assignment, "8:00", "12:00")
        old_assignment = self.a.assignment
        rows.update_row(self.a, specialty=self.uzd)
        self.a.refresh_from_db()
        shift.refresh_from_db()
        self.assertEqual(self.a.assignment.specialty_id, self.uzd.pk)
        self.assertEqual(shift.assignment_id, self.a.assignment_id)
        self.assertNotEqual(old_assignment.pk, self.a.assignment_id)
        self.assertTrue(Assignment.objects.filter(pk=old_assignment.pk).exists())

    def test_specialty_change_into_an_existing_row_is_refused(self):
        self.make_row(
            self.make_assignment(doctor=self.a.assignment.doctor, specialty=self.uzd, rate="0.5")
        )
        with self.assertRaises(rows.RowExists):
            rows.update_row(self.a, specialty=self.uzd)

    def test_bad_rate_is_refused(self):
        with self.assertRaises(rows.RowError):
            rows.update_row(self.a, rate=Decimal("0"))


class CopyRosterTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()

    def test_copies_previous_month_order_and_rates_without_inactive(self):
        january = self.make_schedule(month=1)
        late = self.make_row(self.make_assignment(doctor=self.make_doctor("Яковлев")), january, rate="0.5")
        early = self.make_row(self.make_assignment(doctor=self.make_doctor("Абрамов")), january)
        left = self.make_row(self.make_assignment(doctor=self.make_doctor("Ушёл")), january)
        rows.move_row(late, position=0)
        left.assignment.is_active = False
        left.assignment.save()
        february = self.make_schedule(month=2)
        created = rows.copy_roster(february)
        self.assertEqual([r.assignment_id for r in created], [late.assignment_id, early.assignment_id])
        self.assertEqual([r.rate for r in created], [Decimal("0.5"), Decimal("1.00")])
        self.assertEqual([r.sort_order for r in created], [1, 2])

    def test_skips_empty_months_and_other_departments(self):
        january = self.make_schedule(month=1)
        row = self.make_row(self.make_assignment(doctor=self.make_doctor("Орлов")), january)
        self.make_row(
            self.make_assignment(doctor=self.make_doctor("Чужой"), department=self.dept_b),
            self.make_schedule(self.dept_b, month=2),
        )
        self.make_schedule(month=2)  # пустой, строк нет
        april = self.make_schedule(month=4)
        created = rows.copy_roster(april)
        self.assertEqual([r.assignment_id for r in created], [row.assignment_id])

    def test_without_previous_schedule_takes_active_assignments_by_name(self):
        zed = self.make_assignment(doctor=self.make_doctor("Яковлев"), rate="0.25")
        abe = self.make_assignment(doctor=self.make_doctor("Абрамов"))
        self.make_assignment(doctor=self.make_doctor("Ушёл"), is_active=False)
        created = rows.copy_roster(self.make_schedule())
        self.assertEqual([r.assignment_id for r in created], [abe.pk, zed.pk])
        self.assertEqual(created[1].rate, Decimal("0.25"))

    def test_does_nothing_when_the_schedule_already_has_rows(self):
        schedule = self.make_schedule()
        self.make_row(self.make_assignment(doctor=self.make_doctor("Орлов")), schedule)
        self.make_assignment(doctor=self.make_doctor("Другой"))
        self.assertEqual(rows.copy_roster(schedule), [])
        self.assertEqual(schedule.rows.count(), 1)
