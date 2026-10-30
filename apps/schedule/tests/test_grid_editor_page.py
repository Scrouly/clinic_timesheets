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


class ThreeLineCellTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.assignment = self.make_assignment()
        self.make_row(self.assignment)
        self.make_shift(self.assignment, "9:00", "15:00", day=12)
        self.make_shift(self.assignment, None, None, day=13, kind=self.vacation)
        self.url = reverse("schedule_detail", args=[self.schedule.pk])

    _users = 0

    def html(self, **access):
        type(self)._users += 1
        user = make_access_user(f"viewer{self._users}", **access)
        self.client.login(username=user.username, password=PASSWORD)
        return self.client.get(self.url).content.decode()

    def test_working_shift_shows_hours_cabinet_and_time_in_that_order(self):
        html = self.html(edit=[self.dept_a])
        self.assertRegex(
            html,
            r'<span class="cell__hours">6</span>\s*<span class="cell__cab">301</span>\s*'
            r'<span class="cell__time">09:00–15:00</span>',
        )

    def test_hours_are_an_output_not_a_field(self):
        html = self.html(edit=[self.dept_a])
        grid = html[html.index('<table class="grid"'):html.index("</table>")]
        self.assertNotIn("<input", grid)

    def test_item_has_a_title_for_the_compact_mode(self):
        self.assertIn('title="6 ч, кабинет 301"', self.html(edit=[self.dept_a]))

    def test_absence_is_one_block_with_the_label_only(self):
        html = self.html(edit=[self.dept_a])
        start = html.index("cell__item--kind")
        block = html[start:html.index("</td>", start)]
        self.assertIn("ОТП", block)
        self.assertNotIn("cell__hours", block)
        self.assertNotIn("cell__cab", block)

    def test_value_attribute_is_unchanged(self):
        self.assertIn('data-value="09:00–15:00 · 301"', self.html(edit=[self.dept_a]))

    def test_density_switch_is_there_for_editor_and_viewer(self):
        for access in ({"edit": [self.dept_a]}, {"view": [self.dept_a]}):
            html = self.html(**access)
            self.assertIn("data-density-switch", html)
            self.assertRegex(html, r'data-density-value="detailed"[^>]*aria-pressed="true"')
            self.assertRegex(html, r'data-density-value="compact"[^>]*aria-pressed="false"')
            self.assertIn("js/grid-density.js", html)
            self.assertRegex(html, r'class="grid-wrap[^"]*"[^>]*data-density="detailed"')

    def test_density_switch_is_hidden_until_the_script_runs(self):
        self.assertRegex(self.html(view=[self.dept_a]), r"<div[^>]*data-density-switch[^>]*\bhidden\b")

    def test_grid_markup_has_no_inline_handlers_or_styles(self):
        html = self.html(edit=[self.dept_a])
        grid = html[html.index('<table class="grid"'):html.index("</table>")]
        self.assertNotIn("onclick=", grid)
        self.assertNotIn(" style=", grid)
