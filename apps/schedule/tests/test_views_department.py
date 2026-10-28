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
        self.make_row(self.first, self.schedule)
        self.make_row(self.second, self.schedule)
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


class DepartmentGridNavigationTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.jan = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.feb = Schedule.objects.create(department=self.dept_a, year=2026, month=2)
        self.mar = Schedule.objects.create(department=self.dept_a, year=2026, month=3)
        self.other = Schedule.objects.create(department=self.dept_b, year=2026, month=2)
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.editor = make_access_user("editor", edit=[self.dept_a])
        self.client.login(username=self.editor.username, password=PASSWORD)

    def get(self, schedule):
        return self.client.get(reverse("schedule_detail", args=[schedule.pk]))

    def test_middle_month_links_both_ways(self):
        response = self.get(self.feb)
        self.assertEqual(response.context["prev_schedule"], self.jan)
        self.assertEqual(response.context["next_schedule"], self.mar)
        self.assertContains(response, reverse("schedule_detail", args=[self.jan.pk]))
        self.assertContains(response, reverse("schedule_detail", args=[self.mar.pk]))
        self.assertContains(response, 'aria-label="Предыдущий график: Январь 2026"')
        self.assertContains(response, 'aria-label="Следующий график: Март 2026"')

    def test_other_departments_are_not_used(self):
        response = self.get(self.jan)
        self.assertIsNone(response.context["prev_schedule"])
        self.assertEqual(response.context["next_schedule"], self.feb)
        self.assertNotContains(response, reverse("schedule_detail", args=[self.other.pk]))

    def test_missing_neighbour_is_a_disabled_stub_with_text(self):
        response = self.get(self.jan)
        self.assertContains(response, "Нет предыдущего графика")
        self.assertContains(response, 'aria-disabled="true"')

    def test_add_shift_action_for_editor_only(self):
        self.make_shift(self.assignment, "8:00", "14:00")
        html = self.get(self.feb).content.decode()
        self.assertRegex(html, r'data-panel-link href="[^"]*shifts/new/[^"]*"[^>]*>Добавить смену')
        viewer = make_access_user("looker", view=[self.dept_a])
        self.client.login(username=viewer.username, password=PASSWORD)
        self.assertNotContains(self.get(self.feb), "Добавить смену")

    def test_scroll_modifiers_on_wrapper(self):
        self.make_shift(self.assignment, "8:00", "14:00")
        self.assertContains(self.get(self.jan), "grid-wrap grid-wrap--sums")


class DepartmentGridRowControlsTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.first = self.make_row(self.make_assignment(doctor=self.make_doctor("Абрамов")), self.schedule)
        self.second = self.make_row(self.make_assignment(doctor=self.make_doctor("Беляев")), self.schedule)
        self.url = reverse("schedule_detail", args=[self.schedule.pk])
        self.editor = make_access_user("editor", edit=[self.dept_a])
        self.viewer = make_access_user("looker", view=[self.dept_a])

    def get(self, user):
        self.client.login(username=user.username, password=PASSWORD)
        return self.client.get(self.url)

    def test_editor_gets_menu_and_add_controls_for_every_row(self):
        html = self.get(self.editor).content.decode()
        self.assertEqual(html.count("data-row-menu"), 2)
        # выше первой, ниже каждой строки и «＋ Добавить врача» внизу
        self.assertEqual(html.count("data-row-add"), 4)
        self.assertIn('data-position="0"', html)
        self.assertIn('data-position="2"', html)

    def test_row_ids_and_urls_are_in_the_markup(self):
        html = self.get(self.editor).content.decode()
        self.assertIn(f'id="row-{self.first.pk}"', html)
        self.assertIn(reverse("row_edit", args=[self.schedule.pk, self.first.pk]), html)
        self.assertIn(reverse("row_remove", args=[self.schedule.pk, self.first.pk]), html)
        self.assertIn(reverse("row_move", args=[self.schedule.pk, self.first.pk]), html)

    def test_shift_count_is_on_the_menu_button(self):
        self.make_shift(self.first.assignment, "8:00", "12:00", day=12)
        self.make_shift(self.first.assignment, "8:00", "12:00", day=13)
        html = self.get(self.editor).content.decode()
        self.assertIn('data-shifts="2"', html)
        self.assertIn('data-shifts="0"', html)

    def test_picker_template_and_endpoints_for_editor(self):
        response = self.get(self.editor)
        html = response.content.decode()
        self.assertIn('id="row-picker-template"', html)
        self.assertIn(reverse("schedule_doctors", args=[self.schedule.pk]), html)
        self.assertIn(reverse("row_create", args=[self.schedule.pk]), html)
        self.assertIn("data-csrf=", html)
        self.assertIn("js/grid-rows.js", html)
        self.assertIn(self.surgeon.name, html)  # профессии для выбора в строке-заготовке

    def test_viewer_gets_none_of_it(self):
        html = self.get(self.viewer).content.decode()
        for marker in ("data-row-menu", "data-row-add", "row-picker-template", "grid-rows.js", "row_create"):
            self.assertNotIn(marker, html)
        self.assertNotIn("/rows/new/", html)

    def test_empty_roster_offers_the_first_row_to_an_editor(self):
        self.schedule.rows.all().delete()
        html = self.get(self.editor).content.decode()
        self.assertIn("В графике нет врачей", html)
        self.assertRegex(html, r'data-panel-link href="[^"]*rows/new/[^"]*"[^>]*>Добавить врача')
        self.assertIn("data-panel", html)

    def test_empty_roster_for_a_viewer_is_only_a_message(self):
        self.schedule.rows.all().delete()
        html = self.get(self.viewer).content.decode()
        self.assertIn("В графике нет врачей", html)
        self.assertNotIn("rows/new", html)

    def test_rows_are_numbered_by_a_counter_not_by_markup(self):
        self.assertIn("grid__who", self.get(self.editor).content.decode())
