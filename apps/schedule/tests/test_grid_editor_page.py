from django.test import TestCase
from django.urls import reverse

from apps.core.tests.test_access import PASSWORD

from .helpers import ScheduleTestMixin, make_access_user


class GridEditorPageTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.assignment = self.make_assignment()
        self.row = self.make_row(self.assignment)
        self.make_shift(self.assignment, "9:00", "15:00", day=12)
        self.url = reverse("schedule_detail", args=[self.schedule.pk])

    def page(self, **access):
        user = make_access_user("someone", **access)
        self.client.login(username=user.username, password=PASSWORD)
        return self.client.get(self.url)

    def test_editor_gets_the_cell_editor(self):
        response = self.page(edit=[self.dept_a])
        self.assertContains(response, "data-editor")
        self.assertContains(response, reverse("cell_apply", args=[self.schedule.pk]))
        self.assertContains(response, "js/grid-editor.js")
        self.assertContains(response, 'data-month-gen="января"')
        self.assertContains(response, "data-grid-bar")
        self.assertContains(response, "data-grid-status")

    def test_viewer_gets_a_plain_table(self):
        response = self.page(view=[self.dept_a])
        for marker in ("data-editor", "cell_apply", "grid-editor.js", "data-grid-bar", "data-grid-status"):
            self.assertNotContains(response, marker)
        self.assertNotContains(response, reverse("cell_apply", args=[self.schedule.pk]))

    def test_cells_carry_date_and_canonical_value(self):
        response = self.page(edit=[self.dept_a])
        self.assertContains(response, 'data-date="2026-01-12"')
        self.assertContains(response, 'data-value="09:00–15:00 · 301"')
        self.assertContains(response, f'data-assignment="{self.assignment.pk}"')
        self.assertContains(response, f'data-row="{self.row.pk}"')

    def test_totals_are_addressable(self):
        response = self.page(edit=[self.dept_a])
        for name in ("days", "planned", "norm", "deviation"):
            self.assertContains(response, f'data-sum="{name}"')

    def test_issue_section_is_always_in_the_page(self):
        html = self.page(edit=[self.dept_a]).content.decode()
        self.assertIn("data-issues", html)
        self.assertIn("data-issues-list", html)

    def test_cell_values_are_escaped(self):
        self.cab1.name = '301"><b>'
        self.cab1.save()
        response = self.page(edit=[self.dept_a])
        self.assertNotContains(response, '301"><b>')
