from pathlib import Path

from django import forms
from django.conf import settings
from django.core.management import call_command
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import AccessLevel, Role, User
from apps.core.demo import build_demo_grid
from apps.core.models import Department

from .test_access import PASSWORD, make_user


class TemplateTagTests(SimpleTestCase):
    def render(self, source, **context):
        return Template("{% load ui_tags %}" + source).render(Context(context)).strip()

    def test_known_status_badge(self):
        html = self.render('{% status_badge "review" %}')
        self.assertIn("badge--review", html)
        self.assertIn("На согласовании со специалистом", html)

    def test_unknown_status_is_neutral_and_escaped(self):
        html = self.render("{% status_badge code %}", code="<b>x</b>")
        self.assertIn("badge--unknown", html)
        self.assertNotIn("<b>", html)

    def test_hours_filter(self):
        cases = {169.4: "169,4", 8.0: "8", 6.33: "6,33", "127.05": "127,05", 0: "0", None: "—", "": "—"}
        for value, expected in cases.items():
            self.assertEqual(self.render("{{ v|hours }}", v=value), expected, value)


class DemoGridTests(TestCase):
    def test_days_match_calendar(self):
        self.assertEqual(len(build_demo_grid(2026, 10)["days"]), 31)
        self.assertEqual(len(build_demo_grid(2026, 2)["days"]), 28)
        self.assertEqual(len(build_demo_grid(2028, 2)["days"]), 29)

    def test_weekends_are_marked(self):
        days = build_demo_grid(2026, 10)["days"]
        self.assertEqual([d["weekday"] for d in days[:7]], ["чт", "пт", "сб", "вс", "пн", "вт", "ср"])
        self.assertTrue(days[2]["is_weekend"] and days[3]["is_weekend"])
        self.assertFalse(days[0]["is_weekend"])

    def test_every_row_has_cell_per_day_and_consistent_totals(self):
        grid = build_demo_grid(2026, 10)
        for row in grid["rows"]:
            self.assertEqual(len(row["cells"]), 31)
            shifts = [c for c in row["cells"] if c["kind"] == "shift"]
            self.assertEqual(row["worked_days"], len(shifts))
            self.assertAlmostEqual(row["worked_hours"], sum(c["hours"] for c in shifts), places=2)

    def test_examples_of_each_state_are_present(self):
        cells = [c for r in build_demo_grid(2026, 10)["rows"] for c in r["cells"]]
        self.assertTrue(any(c["kind"] == "vacation" for c in cells))
        self.assertTrue(any(c.get("state") == "error" for c in cells))
        self.assertTrue(any(c.get("state") == "changed" for c in cells))

    def test_examples_present_in_every_month_of_2026(self):
        for month in range(1, 13):
            cells = [c for r in build_demo_grid(2026, month)["rows"] for c in r["cells"]]
            states = {c.get("state") for c in cells} | {c["kind"] for c in cells}
            self.assertTrue({"vacation", "error", "changed"} <= states, month)

    def test_vacation_is_continuous_and_not_counted_as_work(self):
        row = build_demo_grid(2026, 10)["rows"][1]
        self.assertEqual([c["kind"] for c in row["cells"][:5]], ["vacation"] * 5)
        shifts = [c for c in row["cells"] if c["kind"] == "shift"]
        self.assertEqual(row["worked_days"], len(shifts))

    def test_page_renders_for_admin_and_survives_bad_query(self):
        User.objects.create_user("boss", password=PASSWORD, role=Role.ADMIN)
        self.client.login(username="boss", password=PASSWORD)
        response = self.client.get(reverse("demo_grid"), {"year": 2026, "month": 11})
        self.assertContains(response, "Ноябрь 2026")
        self.assertContains(response, "cell--error")
        self.assertEqual(self.client.get(reverse("demo_grid"), {"year": "abc", "month": "13"}).status_code, 200)


class DepartmentAccessUiTests(TestCase):
    def test_topbar_lists_user_departments(self):
        surgery = Department.objects.create(name="Хирургическое отделение")
        make_user("head", Role.HEAD, surgery)
        self.client.login(username="head", password=PASSWORD)
        response = self.client.get(reverse("password_change"))
        self.assertContains(response, "usermenu__meta")
        self.assertContains(response, "Хирургическое отделение")

    def test_seed_demo_gives_edit_access(self):
        call_command("seed_demo", force=True)
        head = User.objects.get(username="head_cons")
        self.assertEqual(head.editable_departments().count(), 2)
        self.assertEqual(
            set(head.department_accesses.values_list("level", flat=True)), {AccessLevel.EDIT}
        )


class BrandShellTests(TestCase):
    def login(self):
        User.objects.create_user("boss", password=PASSWORD, role=Role.ADMIN)
        self.client.login(username="boss", password=PASSWORD)

    def test_shell_shows_brand_logo(self):
        self.login()
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("img/brand/logo.svg", html)
        self.assertIn('alt="CityClinic"', html)

    def test_sidebar_marks_active_page(self):
        self.login()
        self.assertContains(self.client.get(reverse("dashboard")), 'aria-current="page"')

    def test_no_reference_to_old_logo(self):
        base = Path(settings.BASE_DIR)
        self.assertFalse((base / "static" / "img" / "logo.svg").exists())
        for template in (base / "templates").rglob("*.html"):
            self.assertNotIn("img/logo.svg", template.read_text(encoding="utf-8"), template.name)

    def test_login_page_shows_logo(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertIn("img/brand/logo.svg", html)

    def test_error_pages_render_with_logo_and_way_home(self):
        request = RequestFactory().get("/")
        for name in ("403.html", "404.html"):
            html = render_to_string(name, request=request)
            self.assertIn("img/brand/logo.svg", html, name)
            self.assertIn(reverse("dashboard"), html, name)

    def test_unknown_url_gives_404_page(self):
        response = self.client.get("/net-takoj-stranicy/")
        self.assertContains(response, "Страница не найдена", status_code=404)


class FieldAccessibilityTests(SimpleTestCase):
    class SampleForm(forms.Form):
        name = forms.CharField(label="Имя", help_text="Как в паспорте")

    def render(self, data):
        form = self.SampleForm(data)
        return render_to_string("partials/_field.html", {"field": form["name"]})

    def test_error_is_linked_to_input_and_has_text(self):
        html = self.render({"name": ""})
        self.assertIn('aria-invalid="true"', html)
        self.assertRegex(html, r'aria-describedby="[^"]*id_name_error')
        self.assertIn('id="id_name_error"', html)
        self.assertIn("Обязательное поле", html)

    def test_help_is_linked_to_input(self):
        html = self.render({"name": "Иванов"})
        self.assertRegex(html, r'aria-describedby="[^"]*id_name_helptext')
        self.assertIn('id="id_name_helptext"', html)
        self.assertNotIn("aria-invalid", html)
