from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

from apps.core.ui import STATUSES, status_label

register = template.Library()


@register.simple_tag
def status_badge(code, label=None):
    """{% status_badge "review" %} -> цветная плашка статуса."""
    css = code if code in STATUSES else "unknown"
    return format_html('<span class="badge badge--{}">{}</span>', css, label or status_label(code))


@register.filter
def hours(value):
    """169.4 -> «169,4», 8.0 -> «8», 6.33 -> «6,33». Пустое значение -> «—»."""
    if value in (None, ""):
        return "—"
    try:
        number = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return str(value)
    text = f"{number:f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")
