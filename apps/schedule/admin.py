from django.contrib import admin

from apps.core.admin_mixins import AdminHrOnlyMixin

from .models import (
    Assignment,
    Cabinet,
    CalendarDay,
    Doctor,
    MonthNorm,
    Schedule,
    Shift,
    ShiftLengthRule,
    Specialty,
    SpecialtyMonthNorm,
    TimeKind,
)


@admin.register(Cabinet)
class CabinetAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_shared", "in_cabinet_schedule", "is_active")
    list_editable = ("sort_order", "is_shared", "in_cabinet_schedule", "is_active")
    list_filter = ("is_shared", "in_cabinet_schedule", "is_active")
    search_fields = ("name",)


class ShiftLengthRuleInline(AdminHrOnlyMixin, admin.TabularInline):
    model = ShiftLengthRule
    extra = 1


@admin.register(Specialty)
class SpecialtyAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)
    inlines = (ShiftLengthRuleInline,)


class AssignmentInline(AdminHrOnlyMixin, admin.TabularInline):
    model = Assignment
    extra = 1


@admin.register(Doctor)
class DoctorAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("full_name", "tab_number")
    search_fields = ("last_name", "first_name", "patronymic", "tab_number")
    inlines = (AssignmentInline,)


@admin.register(TimeKind)
class TimeKindAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "short_label", "code_1c", "is_working", "is_active")
    list_editable = ("is_active",)


@admin.register(Schedule)
class ScheduleAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("department", "year", "month", "status", "approved_on")
    list_filter = ("department", "year", "status")


@admin.register(Shift)
class ShiftAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("date", "assignment", "kind", "start", "end", "cabinet", "schedule")
    list_filter = ("schedule__department", "kind", "cabinet")
    date_hierarchy = "date"


@admin.register(CalendarDay)
class CalendarDayAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("date", "kind")
    list_filter = ("kind",)
    date_hierarchy = "date"


@admin.register(MonthNorm)
class MonthNormAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("year", "month", "hours")
    list_filter = ("year",)


@admin.register(SpecialtyMonthNorm)
class SpecialtyMonthNormAdmin(AdminHrOnlyMixin, admin.ModelAdmin):
    list_display = ("specialty", "year", "month", "hours")
    list_filter = ("specialty", "year")
