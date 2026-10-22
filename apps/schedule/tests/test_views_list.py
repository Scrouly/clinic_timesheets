from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD, make_user
from apps.schedule.models import Schedule

from .helpers import ScheduleTestMixin


class ScheduleListViewTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule_a = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.schedule_b = Schedule.objects.create(department=self.dept_b, year=2026, month=1)

    def login(self, username, role, *departments):
        make_user(username, role, *departments)
        self.client.login(username=username, password=PASSWORD)

    def test_user_sees_only_visible_departments_schedules(self):
        self.login("head", Role.HEAD, self.dept_a)
        response = self.client.get(reverse("schedules"))
        self.assertEqual(list(response.context["object_list"]), [self.schedule_a])
        self.assertContains(response, reverse("schedule_detail", args=[self.schedule_a.pk]))
        self.assertNotContains(response, reverse("schedule_detail", args=[self.schedule_b.pk]))

    def test_hr_sees_all(self):
        self.login("hr", Role.HR)
        response = self.client.get(reverse("schedules"))
        self.assertEqual(set(response.context["object_list"]), {self.schedule_a, self.schedule_b})

    def test_user_without_access_sees_empty_list(self):
        self.login("nobody", Role.HEAD)
        response = self.client.get(reverse("schedules"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["object_list"]), [])

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("schedules"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('schedules')}")
