from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import DepartmentAccess, User


class DepartmentAccessInline(admin.TabularInline):
    model = DepartmentAccess
    extra = 1


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = (DepartmentAccessInline,)
    list_display = ("username", "full_name_ru", "role", "is_active", "last_login")
    list_filter = ("role", "is_active")
    search_fields = ("username", "last_name", "first_name")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Доступ к графикам", {"fields": ("patronymic", "role")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Доступ к графикам", {"fields": ("last_name", "first_name", "patronymic", "role")}),
    )

    @admin.display(description="ФИО")
    def full_name_ru(self, obj):
        return obj.full_name_ru
