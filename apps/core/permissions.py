"""Права доступа: роли и ограничение по отделениям.

Правило проекта: ограничение по отделению накладывается на выборку данных
(queryset), а не только прячется в меню. Иначе чужой график можно открыть,
подставив номер в адрес страницы.
"""
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(AccessMixin):
    """Пускает только пользователей с одной из ролей из allowed_roles."""

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.has_role(*self.allowed_roles):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DepartmentScopedMixin:
    """Заведующий видит только записи своих отделений, остальные роли все.

    department_field: путь до отделения в модели, например "department"
    или "schedule__department".
    """

    department_field = "department"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.sees_all_departments:
            return queryset
        return queryset.filter(**{f"{self.department_field}__in": user.visible_departments()})
