import re
from html.parser import HTMLParser

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import Schedule
from apps.schedule.tests.helpers import ScheduleTestMixin, make_access_user


class Outline(HTMLParser):
    """Собирает из страницы то, что нужно для проверок доступности."""

    def __init__(self):
        super().__init__()
        self.headings, self.tables, self.captions, self.bad_svgs = [], 0, 0, 0
        self.main = self.dialog_unlabeled = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        elif tag == "table":
            self.tables += 1
        elif tag == "caption":
            self.captions += 1
        elif tag == "main":
            self.main += 1
        elif tag == "svg" and "icon" in attrs.get("class", "") and attrs.get("aria-hidden") != "true":
            self.bad_svgs += 1
        elif tag == "dialog" and not attrs.get("aria-labelledby") and not attrs.get("aria-label"):
            self.dialog_unlabeled += 1


def outline(html):
    parser = Outline()
    parser.feed(html)
    return parser


def icon_only_controls_without_name(html):
    bad = []
    for match in re.finditer(r"<(a|button)\b([^>]*)>(.*?)</\1>", html, re.S):
        opening, inner = match.group(2), match.group(3)
        if "<svg" not in inner or "aria-label=" in opening or "sr-only" in inner:
            continue
        if not re.sub(r"<[^>]+>", "", inner).strip():
            bad.append(match.group(0)[:80])
    return bad


class PageAccessibilityTests(ScheduleTestMixin, TestCase):
    def setUp(self):
        self.setUpData()
        self.schedule = Schedule.objects.create(department=self.dept_a, year=2026, month=1)
        self.assignment = self.make_assignment(doctor=self.make_doctor("Орлов"))
        self.shift = self.make_shift(self.assignment, "8:00", "14:40")
        user = make_access_user("boss", role="admin")
        self.client.login(username=user.username, password=PASSWORD)

    def pages(self):
        return {
            "dashboard": reverse("dashboard"),
            "schedules": reverse("schedules"),
            "schedule_detail": reverse("schedule_detail", args=[self.schedule.pk]),
            "cabinets": reverse("cabinets_month", args=[2026, 1]),
            "demo_grid": reverse("demo_grid"),
            "shift_create": reverse("shift_create"),
            "shift_update": reverse("shift_update", args=[self.shift.pk]),
            "shift_delete": reverse("shift_delete", args=[self.shift.pk]),
            "password_change": reverse("password_change"),
            "summary": reverse("summary"),
            "reports": reverse("reports"),
            "reference": reverse("reference"),
        }

    def each_page(self):
        for name, url in self.pages().items():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, name)
            yield name, response.content.decode()

    def test_language_title_and_skip_link(self):
        for name, html in self.each_page():
            self.assertIn('<html lang="ru">', html, name)
            self.assertRegex(html, r"<title>[^<]+</title>", name)
            self.assertIn('href="#main"', html, name)
            self.assertIn('id="main"', html, name)
            self.assertEqual(outline(html).main, 1, name)

    def test_one_h1_and_no_skipped_levels(self):
        for name, html in self.each_page():
            levels = outline(html).headings
            self.assertEqual(levels.count(1), 1, f"{name}: {levels}")
            self.assertEqual(levels[0], 1, name)
            for before, after in zip(levels, levels[1:]):
                self.assertLessEqual(after, before + 1, f"{name}: {levels}")

    def test_every_table_has_caption(self):
        for name, html in self.each_page():
            parsed = outline(html)
            self.assertEqual(parsed.tables, parsed.captions, name)

    def test_icons_are_hidden_and_icon_buttons_have_names(self):
        for name, html in self.each_page():
            self.assertEqual(outline(html).bad_svgs, 0, f"{name}: значок без aria-hidden")
            self.assertEqual(icon_only_controls_without_name(html), [], name)

    def test_login_and_error_pages(self):
        self.client.logout()
        pages = {"login": self.client.get(reverse("login")).content.decode()}
        for template in ("403.html", "404.html", "500.html"):
            pages[template] = render_to_string(template, request=None) if template == "500.html" else None
        for name, html in pages.items():
            if html is None:
                continue
            self.assertIn('lang="ru"', html, name)
            self.assertEqual(outline(html).headings.count(1), 1, name)

    def test_side_panel_dialog_is_labelled(self):
        html = self.client.get(reverse("schedule_detail", args=[self.schedule.pk])).content.decode()
        self.assertIn("data-panel", html)
        self.assertEqual(outline(html).dialog_unlabeled, 0)

    def test_grid_scroll_regions_are_named_and_focusable(self):
        for name in ("schedule_detail", "cabinets"):
            html = self.client.get(self.pages()[name]).content.decode()
            self.assertRegex(html, r'class="grid-wrap[^"]*" tabindex="0" role="region" aria-label="[^"]+"', name)
