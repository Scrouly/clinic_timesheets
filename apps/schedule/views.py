from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.core.context_processors import MONTHS_NOMINATIVE
from apps.core.permissions import DepartmentScopedMixin

from .forms import ShiftForm
from .grids import build_cabinet_grid, build_department_grid
from .models import Schedule, Shift


def period_title(year, month):
    return f"{MONTHS_NOMINATIVE[month - 1]} {year}"


class ScheduleListView(DepartmentScopedMixin, ListView):
    model = Schedule
    template_name = "schedule/schedule_list.html"
    department_field = "department"

    def get_queryset(self):
        return super().get_queryset().select_related("department")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rows"] = [
            {"schedule": schedule, "title": period_title(schedule.year, schedule.month)}
            for schedule in context["object_list"]
        ]
        return context


class ScheduleDetailView(DepartmentScopedMixin, DetailView):
    model = Schedule
    template_name = "schedule/department_grid.html"
    department_field = "department"

    def get_queryset(self):
        return super().get_queryset().select_related("department")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        schedule = self.object
        context.update(build_department_grid(schedule, self.request.user))
        context["month_title"] = period_title(schedule.year, schedule.month)
        return context


class CabinetAccessMixin(AccessMixin):
    """Общий вид по кабинетам видит любой с общей ролью или с доступом хотя бы к одному отделению."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        user = request.user
        if not (user.sees_all_departments or user.department_accesses.exists()):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class CabinetGridView(CabinetAccessMixin, TemplateView):
    template_name = "schedule/cabinet_grid.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        year = kwargs.get("year", today.year)
        month = kwargs.get("month", today.month)
        try:
            date(year, month, 1)
        except ValueError:
            raise Http404("Нет такого месяца")
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        context.update(build_cabinet_grid(year, month, self.request.user))
        context.update(
            month_title=period_title(year, month),
            prev_url=reverse("cabinets_month", args=[prev_year, prev_month]),
            next_url=reverse("cabinets_month", args=[next_year, next_month]),
        )
        return context


def safe_next(request, default):
    """Куда вернуться после правки: адрес из ?next=, если он ведёт на этот же сайт."""
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


class ShiftFormMixin:
    form_class = ShiftForm
    template_name = "schedule/shift_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.POST.get("next") or self.request.GET.get("next", "")
        return context

    def get_success_url(self):
        return safe_next(self.request, reverse("schedule_detail", args=[self.object.schedule_id]))


class ShiftObjectMixin:
    """Смену открывает тот, кто видит её отделение; менять и удалять может тот, у кого там «редактирование»."""

    def get_object(self, queryset=None):
        shift = get_object_or_404(
            Shift.objects.select_related("schedule__department", "assignment__doctor", "kind", "cabinet"),
            pk=self.kwargs["pk"],
        )
        user = self.request.user
        department_id = shift.schedule.department_id
        if not user.visible_departments().filter(pk=department_id).exists():
            raise Http404
        if not user.editable_departments().filter(pk=department_id).exists():
            raise PermissionDenied
        return shift


class ShiftUpdateView(ShiftObjectMixin, ShiftFormMixin, UpdateView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Изменение смены"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Смена сохранена.")
        return response


class ShiftCreateView(ShiftFormMixin, CreateView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.editable_departments().exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            name: self.request.GET[name]
            for name in ("assignment", "date", "kind", "cabinet")
            if name in self.request.GET
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Новая смена"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Смена добавлена.")
        return response


class ShiftDeleteView(ShiftObjectMixin, DeleteView):
    template_name = "schedule/shift_confirm_delete.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.POST.get("next") or self.request.GET.get("next", "")
        return context

    def get_success_url(self):
        return safe_next(self.request, reverse("schedule_detail", args=[self.object.schedule_id]))

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Смена удалена.")
        return response
