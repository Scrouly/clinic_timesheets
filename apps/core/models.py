from django.db import models


class Department(models.Model):
    """Отделение клиники. К нему привязываются заведующие и графики."""

    name = models.CharField("Название", max_length=100, unique=True)
    short_name = models.CharField("Короткое название", max_length=30, blank=True)
    sort_order = models.PositiveSmallIntegerField("Порядок в списках", default=0)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "отделение"
        verbose_name_plural = "отделения"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name

    @property
    def label(self):
        return self.short_name or self.name
