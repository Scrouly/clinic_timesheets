from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import Schedule

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
