from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import Schedule, Shift

from .helpers import ScheduleTestMixin, make_access_user


class ShiftCreateTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.url = reverse("shift_create")
        self.editor = make_access_user("editor", edit=[self.dept_a])

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def data(self, **overrides):
        data = {
            "assignment": self.assignment.pk,
            "date": "2026-01-14",
            "kind": self.work.pk,
            "start": "09:00",
            "end": "13:00",
            "cabinet": self.cab1.pk,
        }
        data.update(overrides)
        return data

    def test_create_prefilled_from_query(self):
        self.login(self.editor)
        response = self.client.get(
            self.url, {"assignment": self.assignment.pk, "date": "2026-01-14", "cabinet": self.cab2.pk}
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(str(form.initial["assignment"]), str(self.assignment.pk))
        self.assertEqual(form.initial["date"], "2026-01-14")
        self.assertEqual(str(form.initial["cabinet"]), str(self.cab2.pk))

    def test_create_saves_shift_in_matching_schedule(self):
        self.login(self.editor)
        response = self.client.post(self.url, self.data())
        self.assertRedirects(response, reverse("schedule_detail", args=[self.schedule.pk]))
        shift = Shift.objects.get()
        self.assertEqual(shift.schedule, self.schedule)
        self.assertEqual((shift.date, shift.start, shift.end), (date(2026, 1, 14), time(9, 0), time(13, 0)))

    def test_create_without_schedule_shows_error(self):
        self.login(self.editor)
        response = self.client.post(self.url, self.data(date="2026-02-03"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "нет графика")
        self.assertEqual(Shift.objects.count(), 0)

    def test_cannot_create_in_foreign_department(self):
        foreign = self.make_assignment(department=self.dept_b)
        Schedule.objects.create(department=self.dept_b, year=2026, month=1)
        self.login(self.editor)
        response = self.client.post(self.url, self.data(assignment=foreign.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("assignment", response.context["form"].errors)
        self.assertEqual(Shift.objects.count(), 0)

    def test_non_working_kind_is_created_without_times(self):
        self.login(self.editor)
        response = self.client.post(
            self.url, {"assignment": self.assignment.pk, "date": "2026-01-14", "kind": self.vacation.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Shift.objects.get().kind, self.vacation)

    def test_user_without_edit_access_gets_403(self):
        for user in (
            make_access_user("looker", view=[self.dept_a]),
            make_access_user("nobody"),
            make_access_user("see", role=Role.VIEWER),
        ):
            self.login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403, user.username)
            self.assertEqual(self.client.post(self.url, self.data()).status_code, 403, user.username)
        self.assertEqual(Shift.objects.count(), 0)


class EditLinksTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.shift = self.make_shift(self.assignment, "8:00", "14:40")
        self.schedule = Schedule.objects.get(department=self.dept_a, year=2026, month=1)

    def pages(self):
        return (
            reverse("schedule_detail", args=[self.schedule.pk]),
            reverse("cabinets_month", args=[2026, 1]),
        )

    def test_links_present_for_editor(self):
        self.client.login(username=make_access_user("editor", edit=[self.dept_a]).username, password=PASSWORD)
        edit_link = reverse("shift_update", args=[self.shift.pk])
        for url in self.pages():
            self.assertContains(self.client.get(url), edit_link, msg_prefix=url)
        self.assertContains(self.client.get(self.pages()[0]), reverse("shift_create") + "?assignment=")

    def test_links_absent_for_view_only_user(self):
        self.client.login(username=make_access_user("looker", view=[self.dept_a]).username, password=PASSWORD)
        for url in self.pages():
            response = self.client.get(url)
            self.assertNotContains(response, "/edit/", msg_prefix=url)
            self.assertNotContains(response, reverse("shift_create"), msg_prefix=url)
