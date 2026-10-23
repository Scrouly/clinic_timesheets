from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import CalendarDay, DayKind, Schedule

from .helpers import ScheduleTestMixin, make_access_user


class ScheduleDetailViewTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.make_shift(self.assignment, "8:00", "14:40")

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def test_detail_shows_grid_for_visible_department(self):
        self.login(make_access_user("head", view=[self.dept_a]))
        response = self.client.get(reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Орлов И.")
        self.assertContains(response, "08:00–14:40")
        self.assertContains(response, "Январь 2026")

    def test_detail_for_foreign_department_is_404(self):
        self.login(make_access_user("head", view=[self.dept_b]))
        response = self.client.get(reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_without_access_gets_404(self):
        self.login(make_access_user("nobody"))
        response = self.client.get(reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertEqual(response.status_code, 404)

    def test_hr_and_viewer_can_open(self):
        for role in (Role.HR, Role.VIEWER):
            self.login(make_access_user(f"u-{role}", role=role))
            response = self.client.get(reverse("schedule_detail", args=[self.schedule.pk]))
            self.assertEqual(response.status_code, 200, role)


class DepartmentGridMarkupTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.first = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.second = self.make_assignment(doctor=self.make_doctor("Белов"))
        self.url = reverse("schedule_detail", args=[self.schedule.pk])
        self.client.login(username=make_access_user("head", edit=[self.dept_a]).username, password=PASSWORD)

    def get(self, today=date(2026, 1, 12)):
        with patch("apps.schedule.grids.timezone.localdate", return_value=today):
            return self.client.get(self.url)

    def test_grid_marks_today(self):
        html = self.get().content.decode()
        self.assertEqual(html.count('aria-current="date"'), 1)
        self.assertIn("is-today", html)

    def test_no_today_marker_in_other_month(self):
        html = self.get(today=date(2026, 2, 12)).content.decode()
        self.assertNotIn('aria-current="date"', html)

    def test_issue_cell_has_text_alternative_and_flag(self):
        self.make_shift(self.first, "8:00", "14:00")
        self.make_shift(self.second, "10:00", "16:00")  # тот же кабинет и пересекающееся время
        html = self.get().content.decode()
        self.assertIn("cell--error", html)
        self.assertIn("cell__flag", html)
        self.assertIn("Накладка или ошибка", html)

    def test_cell_without_issue_has_no_flag(self):
        self.make_shift(self.first, "8:00", "14:00")
        self.assertNotIn("cell__flag", self.get().content.decode())

    def test_holiday_header_has_class_and_label(self):
        CalendarDay.objects.create(date=date(2026, 1, 1), kind=DayKind.HOLIDAY)
        html = self.get().content.decode()
        self.assertIn("is-holiday", html)
        self.assertIn("праздничный день", html)

    def test_cells_open_in_side_panel_when_editable(self):
        self.make_shift(self.first, "8:00", "14:00")
        html = self.get().content.decode()
        self.assertIn("data-panel-link", html)
        self.assertIn("data-panel", html)
