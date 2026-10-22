from datetime import time

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD
from apps.schedule.checks import CABINET_OVERLAP, check_schedule
from apps.schedule.grids import build_cabinet_grid, build_department_grid
from apps.schedule.models import Schedule, Shift

from .helpers import ScheduleTestMixin, make_access_user


class ShiftEditTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.shift = self.make_shift(self.assignment, "8:00", "14:40")
        self.schedule = Schedule.objects.get(department=self.dept_a, year=2026, month=1)
        self.edit_url = reverse("shift_update", args=[self.shift.pk])
        self.delete_url = reverse("shift_delete", args=[self.shift.pk])
        self.editor = make_access_user("editor", edit=[self.dept_a])

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def data(self, **overrides):
        data = {
            "assignment": self.assignment.pk,
            "date": "2026-01-12",
            "kind": self.work.pk,
            "start": "09:00",
            "end": "15:00",
            "cabinet": self.cab1.pk,
        }
        data.update(overrides)
        return data

    def test_editor_can_update_shift(self):
        self.login(self.editor)
        response = self.client.post(self.edit_url, self.data())
        self.assertRedirects(response, reverse("schedule_detail", args=[self.schedule.pk]))
        self.shift.refresh_from_db()
        self.assertEqual((self.shift.start, self.shift.end), (time(9, 0), time(15, 0)))

    def test_view_only_user_gets_403_and_nothing_changes(self):
        self.login(make_access_user("looker", view=[self.dept_a]))
        self.assertEqual(self.client.get(self.edit_url).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url).status_code, 403)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.start, time(8, 0))

    def test_user_without_access_gets_404(self):
        self.login(make_access_user("nobody"))
        self.assertEqual(self.client.get(self.edit_url).status_code, 404)
        self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 404)

    def test_viewer_role_cannot_edit_but_hr_can(self):
        self.login(make_access_user("see", role=Role.VIEWER))
        self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 403)
        self.login(make_access_user("boss", role=Role.HR))
        self.assertEqual(self.client.post(self.edit_url, self.data()).status_code, 302)

    def test_edit_visible_in_both_views(self):
        self.login(self.editor)
        self.client.post(self.edit_url, self.data())
        department_grid = build_department_grid(self.schedule, self.editor)
        self.assertEqual(department_grid["rows"][0]["cells"][11]["items"][0]["label"], "09:00–15:00")
        cabinet_grid = build_cabinet_grid(2026, 1, self.editor)
        doctor = next(e for e in cabinet_grid["cabinets"] if e["cabinet"] == self.cab1)["doctors"][0]
        self.assertEqual(doctor["cells"][11]["items"][0]["label"], "09:00–15:00")

    def test_invalid_shift_shows_form_error(self):
        self.login(self.editor)
        response = self.client.post(self.edit_url, self.data(end="07:00"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Смена не может переходить через полночь")
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.end, time(14, 40))

    def test_delete_removes_shift(self):
        self.login(self.editor)
        self.assertEqual(self.client.get(self.delete_url).status_code, 200)
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertFalse(Shift.objects.filter(pk=self.shift.pk).exists())

    def test_errors_do_not_block_save(self):
        other = self.make_shift(self.make_assignment(department=self.dept_b), "12:00", "16:00")
        self.login(self.editor)
        response = self.client.post(self.edit_url, self.data(start="09:00", end="13:00"))
        self.assertEqual(response.status_code, 302)
        issues = check_schedule(self.schedule)
        self.assertIn(CABINET_OVERLAP, [i.code for i in issues])
        self.assertTrue(any(other.id in i.shift_ids for i in issues))

    def test_next_param_is_honoured_only_when_safe(self):
        self.login(self.editor)
        back = reverse("cabinets_month", args=[2026, 1])
        response = self.client.post(f"{self.edit_url}?next={back}", self.data())
        self.assertRedirects(response, back)
        response = self.client.post(f"{self.edit_url}?next=//evil.example/", self.data())
        self.assertRedirects(response, reverse("schedule_detail", args=[self.schedule.pk]))

    def test_assignment_choices_limited_to_editable_departments(self):
        foreign = self.make_assignment(department=self.dept_b)
        self.login(self.editor)
        response = self.client.get(self.edit_url)
        choices = response.context["form"].fields["assignment"].queryset
        self.assertIn(self.assignment, choices)
        self.assertNotIn(foreign, choices)
