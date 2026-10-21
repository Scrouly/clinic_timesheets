from django.conf import settings
from django.utils import timezone

from config import __version__

from .navigation import build_nav

MONTHS_NOMINATIVE = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


def site(request):
    """Данные, которые нужны почти каждому шаблону: название, меню, текущий период."""
    today = timezone.localdate()
    context = {
        "APP_TITLE": settings.APP_TITLE,
        "ORG_NAME": settings.ORG_NAME,
        "APP_VERSION": __version__,
        "today": today,
        "current_period": f"{MONTHS_NOMINATIVE[today.month - 1]} {today.year}",
    }
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if user is not None and user.is_authenticated and match is not None:
        current = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
        context["nav_groups"] = build_nav(user, current)
    return context
