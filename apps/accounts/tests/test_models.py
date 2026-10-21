from django.test import TestCase

from apps.accounts.models import Role, User
from apps.core.models import Department


class UserModelTests(TestCase):
    def setUp(self):
        self.diag = Department.objects.create(name="Диагностическое отделение", short_name="Диагностическое")
        self.surg = Department.objects.create(name="Хирургическое отделение")

    def test_superuser_always_gets_admin_role(self):
        user = User.objects.create_superuser("root", password="x")
        self.assertEqual(user.role, Role.ADMIN)

    def test_names(self):
        user = User(username="u", last_name="Иванов", first_name="Иван", patronymic="Петрович")
        self.assertEqual(user.full_name_ru, "Иванов Иван Петрович")
        self.assertEqual(user.short_name_ru, "Иванов И.П.")

    def test_name_falls_back_to_username(self):
        self.assertEqual(User(username="nobody").short_name_ru, "nobody")
        self.assertEqual(User(username="nobody").full_name_ru, "nobody")

    def test_head_sees_only_own_departments(self):
        head = User.objects.create_user("head", role=Role.HEAD)
        head.departments.add(self.diag)
        self.assertEqual(list(head.visible_departments()), [self.diag])
        self.assertFalse(head.sees_all_departments)

    def test_hr_and_viewer_see_all_active_departments(self):
        self.surg.is_active = False
        self.surg.save()
        for role in (Role.HR, Role.VIEWER, Role.ADMIN):
            user = User.objects.create_user(f"u-{role}", role=role)
            self.assertEqual(list(user.visible_departments()), [self.diag])
            self.assertTrue(user.sees_all_departments)

    def test_has_role(self):
        user = User(username="u", role=Role.HR)
        self.assertTrue(user.has_role(Role.HR, Role.ADMIN))
        self.assertFalse(user.has_role(Role.HEAD))
