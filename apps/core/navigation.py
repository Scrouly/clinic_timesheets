"""Левое меню. Один список на всё приложение: пункт виден тем ролям, которые в нём указаны.

Чтобы добавить страницу в меню, добавьте строку в NAV_ITEMS.
Видимость в меню не заменяет проверку прав во view (см. permissions.py).
"""
from dataclasses import dataclass

from django.urls import reverse

from apps.accounts.models import Role

ALL_ROLES = (Role.ADMIN, Role.HR, Role.HEAD, Role.VIEWER)
OVERVIEW_ROLES = (Role.ADMIN, Role.HR, Role.VIEWER)  # видят все отделения
MANAGE_ROLES = (Role.ADMIN, Role.HR)


@dataclass(frozen=True)
class NavItem:
    label: str
    url_name: str
    roles: tuple
    group: str
    icon: str  # id символа в partials/_icons.html
    soon: bool = False  # раздел ещё не готов: в меню остаётся с пометкой «скоро»


NAV_ITEMS = (
    NavItem("Главная", "dashboard", ALL_ROLES, "Работа", "home"),
    NavItem("Графики", "schedules", ALL_ROLES, "Работа", "calendar"),
    NavItem("Сводная", "summary", OVERVIEW_ROLES, "Работа", "table", soon=True),
    NavItem("Кабинеты", "cabinets", ALL_ROLES, "Анализ", "door"),
    NavItem("Отчёты", "reports", OVERVIEW_ROLES, "Анализ", "chart", soon=True),
    NavItem("Справочники", "reference", MANAGE_ROLES, "Настройка", "book", soon=True),
    NavItem("Пользователи", "admin:accounts_user_changelist", (Role.ADMIN,), "Настройка", "users"),
    NavItem("Образец сетки", "demo_grid", (Role.ADMIN,), "Настройка", "grid"),
)


def build_nav(user, current_url_name):
    """Возвращает [{title, items: [{label, url, icon, active, soon}]}] для роли пользователя."""
    groups = {}
    for item in NAV_ITEMS:
        if not user.has_role(*item.roles):
            continue
        groups.setdefault(item.group, []).append(
            {
                "label": item.label,
                "url": reverse(item.url_name),
                "icon": item.icon,
                "active": item.url_name == current_url_name,
                "soon": item.soon,
            }
        )
    return [{"title": title, "items": items} for title, items in groups.items()]
