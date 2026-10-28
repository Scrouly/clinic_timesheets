from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.tests.test_access import PASSWORD

from .helpers import ScheduleTestMixin, make_access_user


class ScheduleAdminRowsTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.hr = make_access_user("hr", role=Role.HR)
        self.hr.is_staff = True  # в admin пускают только сотрудников
        self.hr.save()
        self.client.login(username="hr", password=PASSWORD)

    def add(self, month):
        data = {
            "department": self.dept_a.pk,
            "year": 2026,
            "month": month,
            "status": "draft",
            "rows-TOTAL_FORMS": 0,
            "rows-INITIAL_FORMS": 0,
            "rows-MIN_NUM_FORMS": 0,
            "rows-MAX_NUM_FORMS": 1000,
        }
        return self.client.post(reverse("admin:schedule_schedule_add"), data)

    def test_new_schedule_copies_the_previous_roster(self):
        january = self.make_schedule(month=1)
        self.make_row(self.make_assignment(doctor=self.make_doctor("Орлов"), rate="0.5"), january, rate="0.75")
        response = self.add(2)
        self.assertEqual(response.status_code, 302)
        rows = list(self.make_schedule(month=2).rows.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0].rate), "0.75")

    def test_first_schedule_takes_active_assignments(self):
        self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.add(1)
        self.assertEqual(self.make_schedule(month=1).rows.count(), 1)

    def test_change_page_lists_the_rows(self):
        schedule = self.make_schedule()
        self.make_row(self.make_assignment(doctor=self.make_doctor("Орлов")), schedule)
        response = self.client.get(reverse("admin:schedule_schedule_change", args=[schedule.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Орлов")
