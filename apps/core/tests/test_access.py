from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views.generic import ListView

from apps.accounts.models import Role, User
from apps.core.models import Department
from apps.core.permissions import DepartmentScopedMixin

PASSWORD = "a-long-test-password-1"


def make_user(username, role, *departments):
    user = User.objects.create_user(
        username, password=PASSWORD, role=role, last_name=username.title(), first_name="Тест"
    )
    user.departments.set(departments)
    return user


class LoginTests(TestCase):
    def test_anonymous_is_redirected_to_login(self):
        for name in ("dashboard", "schedules", "demo_grid"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}")

    def test_login_page_is_open(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Вход в систему")

    def test_login_flow_goes_to_dashboard(self):
        make_user("hr", Role.HR)
        response = self.client.post(reverse("login"), {"username": "hr", "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboard"))

    def test_wrong_password_shows_error(self):
        make_user("hr", Role.HR)
        response = self.client.post(reverse("login"), {"username": "hr", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "msg--error")

    def test_logout_requires_post(self):
        make_user("hr", Role.HR)
        self.client.login(username="hr", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))


class NavigationAndRolesTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Хирургическое отделение")
        self.other = Department.objects.create(name="Диагностическое отделение")

    def login(self, username, role, *departments):
        make_user(username, role, *departments)
        self.client.login(username=username, password=PASSWORD)

    def test_head_menu_has_no_manager_sections(self):
        self.login("head", Role.HEAD, self.dept)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(reverse("schedules"), html)
        self.assertNotIn(reverse("summary"), html)
        self.assertNotIn(reverse("reference"), html)
        self.assertNotIn(reverse("demo_grid"), html)

    def test_hr_menu_has_summary_and_reference(self):
        self.login("hr", Role.HR)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn(reverse("summary"), html)
        self.assertIn(reverse("reference"), html)
        self.assertNotIn(reverse("demo_grid"), html)

    def test_admin_menu_has_everything(self):
        self.login("boss", Role.ADMIN)
        html = self.client.get(reverse("dashboard")).content.decode()
        for name in ("summary", "reference", "demo_grid"):
            self.assertIn(reverse(name), html)
        self.assertIn(reverse("admin:accounts_user_changelist"), html)

    def test_current_page_is_marked_in_menu(self):
        self.login("hr", Role.HR)
        html = self.client.get(reverse("summary")).content.decode()
        self.assertIn('aria-current="page"', html)

    def test_head_gets_403_on_manager_pages(self):
        self.login("head", Role.HEAD, self.dept)
        for name in ("summary", "reference", "reports", "demo_grid"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_viewer_cannot_open_reference(self):
        self.login("viewer", Role.VIEWER)
        self.assertEqual(self.client.get(reverse("reference")).status_code, 403)
        self.assertEqual(self.client.get(reverse("summary")).status_code, 200)

    def test_head_dashboard_lists_only_own_departments(self):
        self.login("head", Role.HEAD, self.dept)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Хирургическое отделение")
        self.assertNotContains(response, "Диагностическое отделение")

    def test_head_without_departments_sees_hint(self):
        self.login("head", Role.HEAD)
        self.assertContains(self.client.get(reverse("dashboard")), "не назначено ни одного отделения")

    def test_missing_page_renders_custom_404(self):
        self.login("hr", Role.HR)
        response = self.client.get("/net-takoy-stranicy/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Страница не найдена", status_code=404)

    def test_password_change_page_opens(self):
        self.login("hr", Role.HR)
        self.assertEqual(self.client.get(reverse("password_change")).status_code, 200)


class DepartmentScopeMixinTests(TestCase):
    class View(DepartmentScopedMixin, ListView):
        model = Department
        department_field = "pk"  # у самого отделения «отделение» это его pk

    def setUp(self):
        self.a = Department.objects.create(name="А")
        self.b = Department.objects.create(name="Б")

    def queryset_for(self, user):
        view = self.View()
        view.request = RequestFactory().get("/")
        view.request.user = user
        return list(view.get_queryset().order_by("name"))

    def test_head_is_limited_to_own_departments(self):
        self.assertEqual(self.queryset_for(make_user("h", Role.HEAD, self.a)), [self.a])

    def test_head_without_departments_sees_nothing(self):
        self.assertEqual(self.queryset_for(make_user("h", Role.HEAD)), [])

    def test_hr_sees_everything(self):
        self.assertEqual(self.queryset_for(make_user("r", Role.HR)), [self.a, self.b])
