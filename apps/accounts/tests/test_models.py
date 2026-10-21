import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from apps.accounts.models import AccessLevel, DepartmentAccess, Role, User
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
        DepartmentAccess.objects.create(user=head, department=self.diag, level=AccessLevel.VIEW)
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


class AccessLevelTests(TestCase):
    def setUp(self):
        self.a = Department.objects.create(name="А")
        self.b = Department.objects.create(name="Б")

    def grant(self, user, department, level):
        DepartmentAccess.objects.create(user=user, department=department, level=level)

    def test_copy_departments_creates_edit_rows(self):
        migration = importlib.import_module("apps.accounts.migrations.0003_copy_departments_to_access")
        user = User.objects.create_user("old", role=Role.HEAD)
        user.departments.add(self.a, self.b)
        migration.copy_departments(django_apps, None)
        levels = set(
            DepartmentAccess.objects.filter(user=user).values_list("department_id", "level")
        )
        self.assertEqual(levels, {(self.a.pk, AccessLevel.EDIT), (self.b.pk, AccessLevel.EDIT)})

    def test_levels_are_independent_per_department(self):
        user = User.objects.create_user("u", role=Role.HEAD)
        self.grant(user, self.a, AccessLevel.VIEW)
        self.grant(user, self.b, AccessLevel.EDIT)
        self.assertEqual(list(user.visible_departments()), [self.a, self.b])
        self.assertEqual(list(user.editable_departments()), [self.b])

    def test_user_without_access_sees_nothing(self):
        user = User.objects.create_user("u", role=Role.HEAD)
        self.assertEqual(list(user.visible_departments()), [])
        self.assertEqual(list(user.editable_departments()), [])

    def test_viewer_has_no_editable_departments(self):
        viewer = User.objects.create_user("v", role=Role.VIEWER)
        self.assertEqual(list(viewer.editable_departments()), [])

    def test_hr_and_admin_edit_all_active(self):
        self.b.is_active = False
        self.b.save()
        for role in (Role.HR, Role.ADMIN):
            user = User.objects.create_user(f"u-{role}", role=role)
            self.assertEqual(list(user.editable_departments()), [self.a])
