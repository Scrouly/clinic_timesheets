from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD

from .helpers import ScheduleTestMixin, make_access_user


class CabinetGridViewTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.url = reverse("cabinets_month", args=[2026, 1])
        self.make_shift(self.make_assignment(doctor=self.make_doctor("Орлов")), "8:00", "14:40")

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def test_user_with_any_access_sees_cabinet_grid(self):
        self.login(make_access_user("head", view=[self.dept_b]))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Орлов И.")
        self.assertContains(response, "08:00–14:40")
        self.assertContains(response, "Январь 2026")

    def test_empty_cabinet_column_is_shown(self):
        self.login(make_access_user("head", view=[self.dept_a]))
        self.assertContains(self.client.get(self.url), self.cab2.name)

    def test_user_without_access_gets_403(self):
        self.login(make_access_user("nobody"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_viewer_and_hr_see_grid(self):
        for role in (Role.VIEWER, Role.HR, Role.ADMIN):
            self.login(make_access_user(f"u-{role}", role=role))
            self.assertEqual(self.client.get(self.url).status_code, 200, role)

    def test_default_url_opens_current_month(self):
        self.login(make_access_user("head", view=[self.dept_a]))
        self.assertEqual(self.client.get(reverse("cabinets")).status_code, 200)

    def test_invalid_month_returns_404(self):
        self.login(make_access_user("head", view=[self.dept_a]))
        for month in (0, 13):
            response = self.client.get(reverse("cabinets_month", args=[2026, month]))
            self.assertEqual(response.status_code, 404, month)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("cabinets"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('cabinets')}")


class CabinetGridFilterTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.url = reverse("cabinets_month", args=[2026, 1])
        first = self.make_assignment(doctor=self.make_doctor("Орлов"))
        second = self.make_assignment(doctor=self.make_doctor("Белов"))
        self.make_shift(first, "8:00", "14:00", day=12)
        self.make_shift(second, "10:00", "16:00", day=12)  # накладка в кабинете 301
        self.make_shift(first, "8:00", "14:00", day=13)   # без накладки
        user = make_access_user("head", edit=[self.dept_a])
        self.client.login(username=user.username, password=PASSWORD)

    def test_all_days_by_default(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["day_rows"]), 31)
        self.assertFalse(response.context["issues_only"])
        self.assertContains(response, "?issues=1")

    def test_issues_only_keeps_days_with_issues(self):
        response = self.client.get(self.url, {"issues": "1"})
        rows = response.context["day_rows"]
        self.assertEqual([row["day"]["number"] for row in rows], [12])
        self.assertTrue(response.context["issues_only"])
        self.assertContains(response, "Показать все дни")

    def test_issue_count_is_shown(self):
        self.assertEqual(self.client.get(self.url).context["issue_cells"], 2)

    def test_issues_only_without_issues_shows_message(self):
        response = self.client.get(reverse("cabinets_month", args=[2026, 2]), {"issues": "1"})
        self.assertEqual(response.context["day_rows"], [])
        self.assertContains(response, "накладок нет")

    def test_today_row_is_marked(self):
        with patch("apps.schedule.grids.timezone.localdate", return_value=date(2026, 1, 12)):
            html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count('aria-current="date"'), 1)
        self.assertIn("is-today", html)

    def test_cells_open_in_side_panel(self):
        self.assertContains(self.client.get(self.url), "data-panel-link")


class CabinetGridMarkupTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.make_shift(assignment, "8:00", "14:00", day=12)
        user = make_access_user("head", edit=[self.dept_a])
        self.client.login(username=user.username, password=PASSWORD)
        self.url = reverse("cabinets_month", args=[2026, 1])

    def test_scroll_modifier_on_wrapper(self):
        self.assertContains(self.client.get(self.url), "grid-wrap grid-wrap--by-day")

    def test_filter_labels_are_actions(self):
        self.assertContains(self.client.get(self.url), "Показать только дни с накладками")
        self.assertContains(self.client.get(self.url, {"issues": "1"}), "Показать все дни")
