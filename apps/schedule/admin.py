from django.contrib import admin

from apps.core.admin_mixins import AdminHrOnlyMixin

from .models import Cabinet


@admin.register(Cabinet)
class CabinetAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_shared", "in_cabinet_schedule", "is_active")
    list_editable = ("sort_order", "is_shared", "in_cabinet_schedule", "is_active")
    list_filter = ("is_shared", "in_cabinet_schedule", "is_active")
    search_fields = ("name",)
