from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.accounts.models import Role, User
from apps.core.admin_mixins import AdminHrOnlyMixin
from apps.core.models import Department


class DepartmentTestAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    pass


class AdminHrOnlyMixinTests(TestCase):
    def request_for(self, role, is_staff=True):
        user = User.objects.create_user(f"u-{role}-{is_staff}", role=role, is_staff=is_staff)
        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def setUp(self):
        self.model_admin = DepartmentTestAdmin(Department, AdminSite())

    def test_staff_hr_and_admin_are_allowed(self):
        for role in (Role.HR, Role.ADMIN):
            request = self.request_for(role)
            self.assertTrue(self.model_admin.has_module_permission(request), role)
            self.assertTrue(self.model_admin.has_view_permission(request), role)
            self.assertTrue(self.model_admin.has_add_permission(request), role)
            self.assertTrue(self.model_admin.has_change_permission(request), role)
            self.assertTrue(self.model_admin.has_delete_permission(request), role)

    def test_staff_head_and_viewer_are_denied(self):
        for role in (Role.HEAD, Role.VIEWER):
            request = self.request_for(role)
            self.assertFalse(self.model_admin.has_module_permission(request), role)
            self.assertFalse(self.model_admin.has_change_permission(request), role)

    def test_hr_without_staff_flag_is_denied(self):
        request = self.request_for(Role.HR, is_staff=False)
        self.assertFalse(self.model_admin.has_change_permission(request))
