from datetime import date

from django.views.generic import TemplateView

from apps.accounts.models import Role

from .context_processors import MONTHS_NOMINATIVE
from .demo import build_demo_grid
from .navigation import MANAGE_ROLES, OVERVIEW_ROLES
from .permissions import RoleRequiredMixin


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["departments"] = user.visible_departments()
        context["no_departments"] = user.has_role(Role.HEAD) and not context["departments"]
        return context


class PlaceholderView(RoleRequiredMixin, TemplateView):
    """Страница-заготовка для раздела, который будет сделан на следующих этапах."""

    template_name = "core/placeholder.html"
    title = ""
    lead = ""
    planned = ()
    allowed_roles = ()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(title=self.title, lead=self.lead, planned=self.planned)
        return context


class DemoGridView(RoleRequiredMixin, TemplateView):
    template_name = "core/demo_grid.html"
    allowed_roles = (Role.ADMIN,)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        try:
            year = int(self.request.GET.get("year", today.year))
            month = int(self.request.GET.get("month", today.month))
            date(year, month, 1)
        except (TypeError, ValueError):
            year, month = today.year, today.month
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        context.update(
            build_demo_grid(year, month),
            month_title=f"{MONTHS_NOMINATIVE[month - 1]} {year}",
            prev_query=f"?year={prev_year}&month={prev_month}",
            next_query=f"?year={next_year}&month={next_month}",
        )
        return context


def placeholder(title, lead, planned, roles):
    return PlaceholderView.as_view(title=title, lead=lead, planned=planned, allowed_roles=roles)


SECTIONS = {
    "summary": placeholder(
        "Сводная",
        "Все отделения в одной таблице для кадровика: у кого график готов, у кого на доработке.",
        (
            "статус каждого отделения за месяц и список не сдавших график",
            "норма, запланированные часы и отклонение по каждому врачу",
            "выгрузка в Excel",
        ),
        OVERVIEW_ROLES,
    ),
    "reports": placeholder(
        "Отчёты",
        "Плановые и фактические часы, печатные формы графиков.",
        (
            "план и факт по врачам, специальностям и отделениям",
            "печатная форма с блоками «Согласовано» и «Утверждаю»",
        ),
        OVERVIEW_ROLES,
    ),
    "reference": placeholder(
        "Справочники",
        "Кабинеты, специальности, производственный календарь, правила длины смен.",
        (
            "кабинеты и их названия, под которыми они записаны в старых таблицах",
            "нормы рабочего времени по месяцам",
            "правила длины смены по специальностям",
        ),
        MANAGE_ROLES,
    ),
}
