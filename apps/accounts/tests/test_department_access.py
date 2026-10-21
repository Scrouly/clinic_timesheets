from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.admin import DepartmentAccessInline, UserAdmin
from apps.accounts.models import AccessLevel, DepartmentAccess, Role, User
from apps.core.models import Department


class DepartmentAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", role=Role.HEAD)
        self.department = Department.objects.create(name="Хирургическое отделение")

    def test_pair_user_department_is_unique(self):
        DepartmentAccess.objects.create(user=self.user, department=self.department)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DepartmentAccess.objects.create(user=self.user, department=self.department)

    def test_default_level_is_view(self):
        access = DepartmentAccess.objects.create(user=self.user, department=self.department)
        self.assertEqual(access.level, AccessLevel.VIEW)

    def test_inline_is_on_user_admin(self):
        self.assertIn(DepartmentAccessInline, UserAdmin.inlines)
