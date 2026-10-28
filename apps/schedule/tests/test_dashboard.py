from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD, make_user
from apps.schedule.models import Assignment, Schedule

from .helpers import ScheduleTestMixin


class DashboardDataTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1, status="submitted")
        self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.make_assignment(doctor=self.make_doctor("Белов"))
        self.make_assignment(doctor=self.make_doctor("Уволен"), is_active=False)
        make_user("hr", Role.HR)
        self.client.login(username="hr", password=PASSWORD)

    def get(self):
        with patch("apps.core.views.timezone.localdate", return_value=date(2026, 1, 15)):
            return self.client.get(reverse("dashboard"))

    def rows(self, response):
        return {row["department"].pk: row for row in response.context["rows"]}

    def test_existing_schedule_links_and_shows_status(self):
        response = self.get()
        self.assertContains(response, reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertContains(response, self.schedule.get_status_display())

    def test_missing_schedule_is_marked(self):
        response = self.get()
        self.assertIsNone(self.rows(response)[self.dept_b.pk]["schedule"])
        self.assertContains(response, "Не создан")

    def test_without_a_schedule_active_doctors_are_counted_once(self):
        self.schedule.delete()
        self.assertEqual(self.rows(self.get())[self.dept_a.pk]["doctors"], 2)

    def test_with_a_schedule_doctors_are_counted_by_its_rows(self):
        active = list(Assignment.objects.filter(department=self.dept_a, is_active=True))
        for assignment in active:
            self.make_row(assignment, self.schedule)
        # тот же врач второй строкой (другая профессия) считается один раз
        self.make_row(self.make_assignment(doctor=active[0].doctor, specialty=self.uzd), self.schedule)
        self.assertEqual(self.rows(self.get())[self.dept_a.pk]["doctors"], 2)

    def test_stale_note_is_gone(self):
        self.assertNotContains(self.get(), "когда будет готов раздел")

    def test_head_sees_only_own_departments(self):
        make_user("head", Role.HEAD, self.dept_b)
        self.client.login(username="head", password=PASSWORD)
        response = self.get()
        self.assertEqual(set(self.rows(response)), {self.dept_b.pk})
