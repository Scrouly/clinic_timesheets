from django.apps import apps
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = "admin", "Администратор"
    HR = "hr", "Кадровик"
    HEAD = "head", "Заведующий"
    VIEWER = "viewer", "Наблюдатель"


class User(AbstractUser):
    """Пользовательская модель заводится сразу: заменить её позже очень трудно."""

    patronymic = models.CharField("Отчество", max_length=150, blank=True)
    role = models.CharField("Роль", max_length=10, choices=Role.choices, default=Role.VIEWER)
    departments = models.ManyToManyField(
        "core.Department",
        blank=True,
        related_name="users",
        verbose_name="Отделения",
        help_text="Нужны заведующему: он видит и заполняет только эти отделения.",
    )

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = Role.ADMIN
        super().save(*args, **kwargs)

    # --- отображение имени ---------------------------------------------------
    @property
    def full_name_ru(self):
        parts = [self.last_name, self.first_name, self.patronymic]
        return " ".join(p for p in parts if p) or self.username

    @property
    def short_name_ru(self):
        """«Иванов И.И.» или логин, если ФИО не заполнено."""
        if not self.last_name:
            return self.username
        initials = "".join(f"{p[0]}." for p in (self.first_name, self.patronymic) if p)
        return f"{self.last_name} {initials}".strip()

    # --- роли ----------------------------------------------------------------
    def has_role(self, *roles):
        return self.role in roles

    @property
    def sees_all_departments(self):
        return self.role in (Role.ADMIN, Role.HR, Role.VIEWER)

    def visible_departments(self):
        Department = apps.get_model("core", "Department")
        queryset = Department.objects.filter(is_active=True)
        if self.sees_all_departments:
            return queryset
        return queryset.filter(pk__in=self.departments.values("pk"))
