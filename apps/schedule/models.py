from django.db import models


class Cabinet(models.Model):
    """Кабинет. Одновременная работа нескольких врачей в нём считается накладкой,
    если не отмечено «можно делить» (например, операционная)."""

    name = models.CharField("Название", max_length=50, unique=True)
    sort_order = models.PositiveSmallIntegerField("Порядок в списках", default=0)
    is_shared = models.BooleanField(
        "Можно делить",
        default=False,
        help_text="Одновременная работа нескольких врачей не считается ошибкой.",
    )
    in_cabinet_schedule = models.BooleanField(
        "Показывать в общем графике кабинетов",
        default=True,
        help_text="Снимите галочку, чтобы кабинет не попадал в общий вид по кабинетам.",
    )
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "кабинет"
        verbose_name_plural = "кабинеты"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name
