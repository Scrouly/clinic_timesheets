from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.tests.test_access import PASSWORD
from apps.schedule.models import Assignment, Doctor, ScheduleRow, Shift

from .helpers import ScheduleTestMixin, make_access_user

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}
JSON = {"HTTP_X_REQUESTED_WITH": "fetch", "HTTP_ACCEPT": "application/json"}


class RowViewsBase(ScheduleTestMixin):
    def setUp(self):
        self.setUpData()
        self.schedule = self.make_schedule()
        self.a = self.make_row(self.make_assignment(doctor=self.make_doctor("Абрамов")))
        self.b = self.make_row(self.make_assignment(doctor=self.make_doctor("Беляев")))
        self.editor = make_access_user("editor", edit=[self.dept_a])
        self.client.login(username=self.editor.username, password=PASSWORD)

    def url(self, name, *extra):
        return reverse(name, args=[self.schedule.pk, *extra])

    def order(self):
        return [r.assignment.doctor.last_name for r in self.schedule.rows.order_by("sort_order")]

    def messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]


class AccessTests(RowViewsBase, TestCase):
    def endpoints(self):
        return [
            ("get", self.url("schedule_doctors")),
            ("get", self.url("row_create")),
            ("post", self.url("row_create")),
            ("get", self.url("row_edit", self.a.pk)),
            ("post", self.url("row_edit", self.a.pk)),
            ("get", self.url("row_remove", self.a.pk)),
            ("post", self.url("row_remove", self.a.pk)),
            ("post", self.url("row_move", self.a.pk)),
        ]

    def test_viewer_of_the_department_is_refused_everywhere(self):
        viewer = make_access_user("looker", view=[self.dept_a])
        self.client.login(username=viewer.username, password=PASSWORD)
        for method, url in self.endpoints():
            self.assertEqual(getattr(self.client, method)(url, {}).status_code, 403, (method, url))

    def test_editor_of_another_department_is_refused(self):
        stranger = make_access_user("stranger", edit=[self.dept_b])
        self.client.login(username=stranger.username, password=PASSWORD)
        for method, url in self.endpoints():
            self.assertEqual(getattr(self.client, method)(url, {}).status_code, 403, (method, url))
        self.assertEqual(self.schedule.rows.count(), 2)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        for method, url in self.endpoints():
            response = getattr(self.client, method)(url, {})
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("login", response["Location"])

    def test_unknown_schedule_is_404(self):
        self.assertEqual(self.client.get(reverse("row_create", args=[9999])).status_code, 404)

    def test_row_of_another_schedule_is_404(self):
        other = self.make_row(
            self.make_assignment(doctor=self.make_doctor("Чужой")), self.make_schedule(month=2)
        )
        self.assertEqual(self.client.get(self.url("row_edit", other.pk)).status_code, 404)

    def test_posts_without_csrf_token_are_refused(self):
        strict = Client(enforce_csrf_checks=True)
        strict.login(username=self.editor.username, password=PASSWORD)
        response = strict.post(self.url("row_move", self.a.pk), {"direction": "down"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.order(), ["Абрамов", "Беляев"])

    def test_admin_and_hr_may_edit_any_schedule(self):
        for role in ("admin", "hr"):
            user = make_access_user(f"u{role}", role=role)
            self.client.login(username=user.username, password=PASSWORD)
            self.assertEqual(self.client.get(self.url("row_create")).status_code, 200, role)


class DoctorSearchTests(RowViewsBase, TestCase):
    def setUp(self):
        super().setUp()
        self.kn = Doctor.objects.create(
            last_name="Князев", first_name="Павел", patronymic="Олегович", tab_number="1234"
        )
        self.ko = Doctor.objects.create(last_name="Коваль", first_name="Ольга", tab_number="5678")
        self.make_assignment(doctor=self.kn, specialty=self.uzd, rate="0.75")  # в этом отделении
        self.make_assignment(doctor=self.ko, department=self.dept_b, specialty=self.surgeon, rate="0.5")

    def search(self, q=""):
        response = self.client.get(self.url("schedule_doctors"), {"q": q})
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_search_is_case_insensitive_by_surname_prefix(self):
        self.assertEqual([r["id"] for r in self.search("кн")], [self.kn.pk])

    def test_search_by_first_name_patronymic_and_tab_number(self):
        self.assertEqual([r["id"] for r in self.search("павел")], [self.kn.pk])
        self.assertEqual([r["id"] for r in self.search("олегович")], [self.kn.pk])
        self.assertEqual([r["id"] for r in self.search("5678")], [self.ko.pk])

    def test_several_words_must_all_match(self):
        self.assertEqual([r["id"] for r in self.search("кня пав")], [self.kn.pk])
        self.assertEqual(self.search("кня оль"), [])

    def test_empty_query_lists_people_alphabetically(self):
        names = [r["name"] for r in self.search("")]
        self.assertEqual(names, sorted(names))
        self.assertGreaterEqual(len(names), 4)

    def test_result_is_limited(self):
        for index in range(30):
            Doctor.objects.create(last_name=f"Яяя{index:02d}", first_name="Иван")
        self.assertEqual(len(self.search("яяя")), 20)

    def test_fields_and_suggestion_from_this_department(self):
        result = self.search("князев")[0]
        self.assertEqual(result["name"], "Князев Павел Олегович")
        self.assertEqual(result["short"], "Князев П.О.")
        self.assertEqual(result["tab_number"], "1234")
        self.assertEqual((result["specialty"], result["rate"]), (self.uzd.pk, "0.75"))

    def test_suggestion_falls_back_to_other_departments_specialty(self):
        result = self.search("коваль")[0]
        self.assertEqual((result["specialty"], result["rate"]), (self.surgeon.pk, "1"))

    def test_person_without_assignments_has_no_suggestion(self):
        Doctor.objects.create(last_name="Новиков", first_name="Иван")
        result = self.search("новиков")[0]
        self.assertEqual((result["specialty"], result["rate"]), (None, "1"))

    def test_already_present_specialties_are_listed(self):
        ScheduleRow.ensure(self.schedule, Assignment.objects.get(doctor=self.kn, department=self.dept_a))
        self.assertEqual(self.search("князев")[0]["in_schedule"], [self.uzd.pk])
        self.assertEqual(self.search("коваль")[0]["in_schedule"], [])


class RowCreateTests(RowViewsBase, TestCase):
    def setUp(self):
        super().setUp()
        self.person = Doctor.objects.create(last_name="Герасимов", first_name="Пётр", tab_number="9")

    def post(self, headers=JSON, **overrides):
        data = {"doctor": self.person.pk, "specialty": self.uzd.pk, "rate": "0.75"}
        data.update(overrides)
        return self.client.post(self.url("row_create"), data, **headers)

    def test_json_success_creates_the_row_at_the_position(self):
        response = self.post(position=1)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(self.order(), ["Абрамов", "Герасимов", "Беляев"])
        self.assertEqual(ScheduleRow.objects.get(pk=body["row"]).rate, Decimal("0.75"))

    def test_without_position_the_row_goes_last(self):
        self.post()
        self.assertEqual(self.order()[-1], "Герасимов")

    def test_comma_decimal_is_accepted(self):
        self.post(rate="0,5")
        self.assertEqual(self.schedule.rows.get(assignment__doctor=self.person).rate, Decimal("0.50"))

    def test_duplicate_is_reported_as_json_error(self):
        self.post()
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("уже есть в графике", " ".join(response.json()["errors"]["__all__"]))
        self.assertEqual(self.schedule.rows.count(), 3)

    def test_bad_rate_and_missing_doctor_are_field_errors(self):
        errors = self.post(rate="3", doctor="").json()["errors"]
        self.assertIn("rate", errors)
        self.assertIn("doctor", errors)
        self.assertEqual(self.schedule.rows.count(), 2)

    def test_inactive_specialty_cannot_be_chosen(self):
        self.uzd.is_active = False
        self.uzd.save()
        self.assertIn("specialty", self.post().json()["errors"])

    def test_form_partial_for_the_panel(self):
        response = self.client.get(self.url("row_create"), {"position": 1}, **FETCH)
        html = response.content.decode()
        self.assertNotIn("<html", html)
        self.assertIn('name="doctor"', html)
        self.assertIn('name="position" value="1"', html)
        self.assertIn("data-panel-form", html)

    def test_full_page_without_header_and_redirect_on_success(self):
        page = self.client.get(self.url("row_create"))
        self.assertIn("<html", page.content.decode())
        response = self.post(headers={})
        self.assertRedirects(response, reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertIn("Герасимов", " ".join(self.messages(response)))

    def test_panel_post_returns_json_on_success_and_form_with_errors_otherwise(self):
        ok = self.client.post(
            self.url("row_create"), {"doctor": self.person.pk, "specialty": self.uzd.pk, "rate": "1"}, **FETCH
        )
        self.assertTrue(ok.json()["ok"])
        bad = self.client.post(self.url("row_create"), {"doctor": "", "specialty": "", "rate": ""}, **FETCH)
        self.assertEqual(bad.status_code, 200)
        self.assertIn("field__error", bad.content.decode())

    def test_only_existing_catalog_entries_are_accepted(self):
        self.assertIn("doctor", self.post(doctor=99999).json()["errors"])
        self.assertEqual(Doctor.objects.filter(last_name="Герасимов").count(), 1)
        self.assertEqual(Doctor.objects.count(), 3)  # новых врачей заведующий создать не может


class RowEditTests(RowViewsBase, TestCase):
    def test_form_is_prefilled(self):
        html = self.client.get(self.url("row_edit", self.a.pk), **FETCH).content.decode()
        self.assertNotIn("<html", html)
        self.assertIn('name="rate"', html)
        self.assertIn('name="specialty"', html)
        self.assertIn("Абрамов", html)

    def test_catalog_note_is_not_shown_when_only_rate_is_edited(self):
        html = self.client.get(self.url("row_edit", self.a.pk), **FETCH).content.decode()
        self.assertNotIn("заводит кадровик", html)
        create = self.client.get(self.url("row_create"), **FETCH).content.decode()
        self.assertIn("заводит кадровик", create)

    def test_rate_change_is_for_this_month_only(self):
        february = self.make_row(self.a.assignment, self.make_schedule(month=2))
        response = self.client.post(
            self.url("row_edit", self.a.pk), {"specialty": self.surgeon.pk, "rate": "0.5"}, **FETCH
        )
        self.assertTrue(response.json()["ok"])
        self.a.refresh_from_db()
        february.refresh_from_db()
        self.assertEqual(self.a.rate, Decimal("0.5"))
        self.assertEqual(february.rate, Decimal("1.00"))

    def test_specialty_change_moves_the_month_shifts(self):
        shift = self.make_shift(self.a.assignment, "8:00", "12:00")
        self.client.post(self.url("row_edit", self.a.pk), {"specialty": self.uzd.pk, "rate": "1"}, **FETCH)
        shift.refresh_from_db()
        self.assertEqual(shift.assignment.specialty_id, self.uzd.pk)

    def test_clash_with_an_existing_row_is_a_form_error(self):
        self.make_row(self.make_assignment(doctor=self.a.assignment.doctor, specialty=self.uzd))
        response = self.client.post(
            self.url("row_edit", self.a.pk), {"specialty": self.uzd.pk, "rate": "1"}, **FETCH
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("уже есть в графике", response.content.decode())

    def test_bad_rate_is_a_form_error(self):
        response = self.client.post(
            self.url("row_edit", self.a.pk), {"specialty": self.surgeon.pk, "rate": "9"}, **FETCH
        )
        self.assertIn("field__error", response.content.decode())
        self.a.refresh_from_db()
        self.assertEqual(self.a.rate, Decimal("1.00"))


class RowRemoveTests(RowViewsBase, TestCase):
    def test_confirmation_text_names_the_person_and_the_shifts(self):
        self.make_shift(self.a.assignment, "8:00", "12:00", day=12)
        self.make_shift(self.a.assignment, "8:00", "12:00", day=13)
        html = self.client.get(self.url("row_remove", self.a.pk), **FETCH).content.decode()
        self.assertIn("Абрамов", html)
        self.assertIn("за Январь 2026", html)
        self.assertIn("2 смены", html)
        self.assertIn('name="confirm" value="2"', html)

    def test_empty_row_text_has_no_shift_warning(self):
        html = self.client.get(self.url("row_remove", self.b.pk), **FETCH).content.decode()
        self.assertNotIn("смен", html.split("<form")[1].split("</p>")[0])

    def test_confirmed_removal_deletes_row_and_month_shifts(self):
        self.make_shift(self.a.assignment, "8:00", "12:00")
        response = self.client.post(self.url("row_remove", self.a.pk), {"confirm": "1"}, **FETCH)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.order(), ["Беляев"])
        self.assertFalse(Shift.objects.filter(schedule=self.schedule).exists())

    def test_wrong_confirmation_is_refused(self):
        self.make_shift(self.a.assignment, "8:00", "12:00")
        response = self.client.post(self.url("row_remove", self.a.pk), {"confirm": "0"}, **FETCH)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Подтвердите удаление", html)
        self.assertIn('name="confirm" value="1"', html)  # в повторной форме верное число
        self.assertEqual(self.schedule.rows.count(), 2)

    def test_empty_row_goes_without_a_number(self):
        response = self.client.post(self.url("row_remove", self.b.pk), {}, **FETCH)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.order(), ["Абрамов"])

    def test_page_version_redirects_with_a_message(self):
        response = self.client.post(self.url("row_remove", self.b.pk), {"confirm": "0"})
        self.assertRedirects(response, reverse("schedule_detail", args=[self.schedule.pk]))
        self.assertIn("Беляев", " ".join(self.messages(response)))


class RowMoveTests(RowViewsBase, TestCase):
    def test_move_down_and_up(self):
        self.assertTrue(self.client.post(self.url("row_move", self.a.pk), {"direction": "down"}, **FETCH).json()["ok"])
        self.assertEqual(self.order(), ["Беляев", "Абрамов"])
        self.client.post(self.url("row_move", self.a.pk), {"direction": "up"}, **FETCH)
        self.assertEqual(self.order(), ["Абрамов", "Беляев"])

    def test_move_to_position(self):
        self.client.post(self.url("row_move", self.b.pk), {"position": "0"}, **FETCH)
        self.assertEqual(self.order(), ["Беляев", "Абрамов"])

    def test_unclear_request_is_a_json_error(self):
        response = self.client.post(self.url("row_move", self.a.pk), {}, **FETCH)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url("row_move", self.a.pk)).status_code, 405)
