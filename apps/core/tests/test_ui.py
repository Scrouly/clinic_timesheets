from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
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
