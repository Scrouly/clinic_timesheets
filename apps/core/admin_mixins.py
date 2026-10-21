"""Права в административном сайте для справочников графиков."""
from apps.accounts.models import Role


class AdminHrOnlyMixin:
    """Справочник доступен в admin только сотрудникам (is_staff) с ролью admin или hr."""

    def _allowed(self, request):
        user = request.user
        return bool(user.is_active and user.is_staff and user.has_role(Role.ADMIN, Role.HR))

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return self._allowed(request)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request)

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request)
