from datetime import date

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


class ScheduleListFilterTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.jan_a = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.jan_b = Schedule.objects.create(department=self.dept_b, year=2026, month=1)
        self.feb_a = Schedule.objects.create(
            department=self.dept_a, year=2026, month=2, status="approved", approved_on=date(2026, 2, 27)
        )
        make_user("hr", Role.HR)
        self.client.login(username="hr", password=PASSWORD)
        self.url = reverse("schedules")

    def ids(self, response):
        return {schedule.pk for schedule in response.context["object_list"]}

    def test_status_is_shown_as_text(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.feb_a.get_status_display())
        self.assertContains(response, self.jan_a.get_status_display())

    def test_approval_date_is_shown(self):
        self.assertContains(self.client.get(self.url), "27.02.2026")

    def test_filter_by_department(self):
        response = self.client.get(self.url, {"department": self.dept_b.pk})
        self.assertEqual(self.ids(response), {self.jan_b.pk})

    def test_filter_by_period(self):
        response = self.client.get(self.url, {"period": "2026-02"})
        self.assertEqual(self.ids(response), {self.feb_a.pk})

    def test_filters_combine(self):
        response = self.client.get(self.url, {"department": self.dept_a.pk, "period": "2026-01"})
        self.assertEqual(self.ids(response), {self.jan_a.pk})

    def test_broken_filter_values_are_ignored(self):
        response = self.client.get(self.url, {"department": "abc", "period": "2026-13"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ids(response), {self.jan_a.pk, self.jan_b.pk, self.feb_a.pk})

    def test_filter_options_only_for_visible_departments(self):
        make_user("head", Role.HEAD, self.dept_a)
        self.client.login(username="head", password=PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual([d.pk for d in response.context["filter_departments"]], [self.dept_a.pk])
        self.assertNotContains(response, f'value="{self.dept_b.pk}"')

    def test_foreign_department_in_filter_shows_nothing_extra(self):
        make_user("head", Role.HEAD, self.dept_a)
        self.client.login(username="head", password=PASSWORD)
        response = self.client.get(self.url, {"department": self.dept_b.pk})
        self.assertEqual(self.ids(response), set())

    def test_empty_result_offers_reset(self):
        response = self.client.get(self.url, {"period": "2025-05"})
        self.assertContains(response, "выбранным условиям графиков нет")
        self.assertContains(response, "Сбросить")

    def test_period_options_are_listed_newest_first(self):
        response = self.client.get(self.url)
        self.assertEqual([p["value"] for p in response.context["filter_periods"]], ["2026-02", "2026-01"])
