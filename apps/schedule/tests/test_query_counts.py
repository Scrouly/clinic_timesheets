from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.tests.test_access import PASSWORD
from apps.schedule.checks import check_schedule
from apps.schedule.models import Schedule, Specialty

from .helpers import ScheduleTestMixin, make_access_user


class QueryCountTests(ScheduleTestMixin, TestCase):
    """Число запросов не растёт вместе с числом смен и врачей."""

    def setUp(self):
        self.setUpData()
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        user = make_access_user("boss", role="admin")
        self.client.login(username=user.username, password=PASSWORD)

    def count(self, call):
        with CaptureQueriesContext(connection) as queries:
            call()
        return len(queries)

    def fill(self, doctors, days):
        for index in range(doctors):
            assignment = self.make_assignment(doctor=self.make_doctor(f"Врач{index}{'абвгде'[index % 6]}"))
            for day in range(1, days + 1):
                self.make_shift(assignment, "8:00", "13:00", day=day)

    def test_checks_do_not_query_per_shift(self):
        self.fill(1, 2)
        few = self.count(lambda: check_schedule(self.schedule))
        self.fill(1, 12)
        many = self.count(lambda: check_schedule(self.schedule))
        self.assertEqual(few, many)

    def test_checks_do_not_query_per_doctor(self):
        self.fill(1, 3)
        few = self.count(lambda: check_schedule(self.schedule))
        self.fill(5, 3)
        many = self.count(lambda: check_schedule(self.schedule))
        self.assertEqual(few, many)

    def test_cabinet_page_query_count_is_flat(self):
        url = reverse("cabinets_month", args=[2026, 1])
        self.fill(1, 2)
        few = self.count(lambda: self.client.get(url))
        self.fill(4, 10)
        many = self.count(lambda: self.client.get(url))
        self.assertEqual(few, many)

    def test_department_page_query_count_is_flat(self):
        url = reverse("schedule_detail", args=[self.schedule.pk])
        self.fill(1, 2)
        few = self.count(lambda: self.client.get(url))
        self.fill(4, 10)
        many = self.count(lambda: self.client.get(url))
        self.assertEqual(few, many)

    def test_rule_lookup_uses_prefetched_rules(self):
        assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        specialty = Specialty.objects.prefetch_related("length_rules").get(pk=assignment.specialty_id)
        self.assertEqual(self.count(lambda: specialty.rule_for_rate(1)), 0)
