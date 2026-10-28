import json
from decimal import Decimal

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import MonthNorm, ScheduleStatus, Shift

from .helpers import ScheduleTestMixin, make_access_user


class CellViewBase(ScheduleTestMixin):
    def setUp(self):
        self.setUpData()
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("10"))
        self.schedule = self.make_schedule()
        self.assignment = self.make_assignment(rate="0.5")
        self.row = self.make_row(self.assignment)
        self.editor = make_access_user("editor", edit=[self.dept_a])
        self.client.login(username=self.editor.username, password=PASSWORD)
        self.url = reverse("cell_apply", args=[self.schedule.pk])

    def post(self, raw, day="2026-01-12", row=None, expected=None, client=None, **extra):
        body = {"row": (row or self.row).pk, "date": day, "raw": raw}
        if expected is not None:
            body["expected"] = expected
        body.update(extra)
        return (client or self.client).post(self.url, json.dumps(body), content_type="application/json")


class AccessTests(CellViewBase, TestCase):
    def test_viewer_is_refused(self):
        viewer = make_access_user("looker", view=[self.dept_a])
        self.client.login(username=viewer.username, password=PASSWORD)
        self.assertEqual(self.post("9-15 301").status_code, 403)
        self.assertEqual(Shift.objects.count(), 0)

    def test_editor_of_another_department_is_refused(self):
        stranger = make_access_user("stranger", edit=[self.dept_b])
        self.client.login(username=stranger.username, password=PASSWORD)
        self.assertEqual(self.post("9-15 301").status_code, 403)
        self.assertEqual(Shift.objects.count(), 0)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.post("9-15 301")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_unknown_schedule_is_404(self):
        response = self.client.post(reverse("cell_apply", args=[9999]), "{}", content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_row_of_another_schedule_is_404(self):
        other = self.make_row(self.make_assignment(), self.make_schedule(month=2))
        self.assertEqual(self.post("9-15 301", row=other).status_code, 404)
        self.assertEqual(Shift.objects.count(), 0)

    def test_post_without_csrf_token_is_refused(self):
        strict = Client(enforce_csrf_checks=True)
        strict.login(username=self.editor.username, password=PASSWORD)
        self.assertEqual(self.post("9-15 301", client=strict).status_code, 403)
        self.assertEqual(Shift.objects.count(), 0)

    def test_editor_may_change_an_approved_schedule(self):
        self.schedule.status = ScheduleStatus.APPROVED
        self.schedule.save()
        self.assertEqual(self.post("9-15 301").status_code, 200)

    def test_viewer_role_is_refused_even_with_access_rows(self):
        looker = make_access_user("lookrole", role="viewer", edit=[self.dept_a])
        self.client.login(username=looker.username, password=PASSWORD)
        self.assertEqual(self.post("9-15 301").status_code, 403)

    def test_hr_edits_any_department(self):
        hr = make_access_user("kadr", role="hr")
        self.client.login(username=hr.username, password=PASSWORD)
        self.assertEqual(self.post("9-15 301").status_code, 200)


class ResponseTests(CellViewBase, TestCase):
    def test_saved_cell_answer(self):
        response = self.post("9-15 301")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        shift = Shift.objects.get()
        self.assertTrue(data["ok"])
        self.assertEqual(data["cell"]["value"], "09:00–15:00 · 301")
        self.assertEqual(data["cell"]["kind"], "shift")
        self.assertEqual(data["cell"]["items"], [{"label": "09:00–15:00", "cabinet": "301"}])
        self.assertEqual(data["cell"]["panel_url"], reverse("shift_update", args=[shift.pk]))

    def test_empty_cell_answer_points_to_the_create_form(self):
        data = self.post("").json()
        self.assertEqual(data["cell"]["kind"], "off")
        self.assertEqual(data["cell"]["items"], [])
        self.assertIn("assignment=%d" % self.assignment.pk, data["cell"]["panel_url"])
        self.assertIn("date=2026-01-12", data["cell"]["panel_url"])

    def test_absence_kind(self):
        data = self.post("отп").json()
        self.assertEqual(data["cell"]["kind"], "absence")
        self.assertEqual(data["cell"]["items"], [{"label": "ОТП", "cabinet": ""}])

    def test_row_totals_follow_the_saved_cell(self):
        self.post("8-13 301", day="2026-01-12")
        data = self.post("8-14 301", day="2026-01-13").json()
        expected = {
            "assignment": self.assignment.pk,
            "days": 2,
            "planned": "11",
            "norm": "5",
            "deviation": "6",
            "deviation_sign": 1,
        }
        self.assertEqual(data["row"], expected)

    def test_row_without_norm(self):
        MonthNorm.objects.all().delete()
        row = self.post("8-13 301").json()["row"]
        self.assertEqual(row["norm"], "—")
        self.assertEqual(row["deviation_sign"], 0)

    def test_issues_state_lists_cells_and_messages(self):
        other = self.make_assignment()
        self.make_row(other)
        self.make_shift(other, "9:00", "13:00", day=12, cabinet=self.cab1)
        issues = self.post("10-14 301").json()["issues"]
        self.assertIn({"assignment": self.assignment.pk, "date": "2026-01-12"}, issues["cells"])
        self.assertIn({"assignment": other.pk, "date": "2026-01-12"}, issues["cells"])
        self.assertTrue(any("Кабинет 301" in message for message in issues["messages"]))

    def test_issue_is_gone_after_the_fix(self):
        other = self.make_assignment()
        self.make_row(other)
        self.make_shift(other, "9:00", "13:00", day=12, cabinet=self.cab1)
        self.post("10-14 301")
        issues = self.post("10-14 302").json()["issues"]
        self.assertFalse(any(c["date"] == "2026-01-12" for c in issues["cells"]))

    def test_hours_norm_problem_marks_the_row(self):
        issues = self.post("8-12 301").json()["issues"]
        self.assertEqual(issues["norm_rows"], [self.assignment.pk])


class ErrorTests(CellViewBase, TestCase):
    def test_unclear_text_is_422_with_a_hint(self):
        self.make_shift(self.assignment, "8:00", "12:00", day=12)
        response = self.post("8-")
        self.assertEqual(response.status_code, 422)
        self.assertIn("Не понял «8-»", response.json()["error"])
        self.assertEqual(Shift.objects.get().end.hour, 12)

    def test_conflict_is_409_with_the_current_value(self):
        self.make_shift(self.assignment, "8:00", "14:00", day=12)
        response = self.post("9-15 301", expected="")
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual((data["ok"], data["conflict"], data["current"]), (False, True, "08:00–14:00 · 301"))
        self.assertEqual(data["cell"]["items"], [{"label": "08:00–14:00", "cabinet": "301"}])
        self.assertEqual(data["cell"]["kind"], "shift")

    def test_malformed_requests_are_400(self):
        def raw(body):
            return self.client.post(self.url, body, content_type="application/json").status_code

        self.assertEqual(raw("не json"), 400)
        self.assertEqual(raw("[]"), 400)
        self.assertEqual(raw(json.dumps({"row": "x", "date": "2026-01-12", "raw": ""})), 400)
        self.assertEqual(raw(json.dumps({"row": self.row.pk, "date": "вчера", "raw": ""})), 400)
        self.assertEqual(raw(json.dumps({"row": self.row.pk, "date": "2026-01-12", "raw": 5})), 400)
        self.assertEqual(raw(json.dumps({"row": self.row.pk, "date": "2026-01-12", "raw": "x" * 500})), 400)
        self.assertEqual(raw(json.dumps({"row": self.row.pk, "date": "2026-01-12", "raw": "", "expected": 1})), 400)

    def test_date_outside_the_month_is_422(self):
        self.assertEqual(self.post("9-15 301", day="2026-02-03").status_code, 422)


class QueryCountTests(CellViewBase, TestCase):
    def count(self, call):
        with CaptureQueriesContext(connection) as queries:
            call()
        return len(queries)

    def fill(self, doctors, first=0):
        """Врачи со сменами почти на весь месяц; из-за общего кабинета в графике есть накладки."""
        for index in range(first, first + doctors):
            other = self.make_assignment(doctor=self.make_doctor(f"Другой{index}"))
            for day in range(1, 20):
                self.make_shift(other, "8:00", "12:00", day=day, cabinet=self.cab2)

    def test_query_count_does_not_grow_with_the_month(self):
        self.fill(2)
        few = self.count(lambda: self.post("8-12 302", day="2026-01-06"))
        self.fill(6, first=2)
        many = self.count(lambda: self.post("8-12 302", day="2026-01-07"))
        self.assertEqual(few, many)
