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
