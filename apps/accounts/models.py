from django.apps import apps
from django.conf import settings
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
        return queryset.filter(pk__in=self.department_accesses.values("department_id"))

    def editable_departments(self):
        """Отделения, в которых пользователь может менять графики."""
        Department = apps.get_model("core", "Department")
        queryset = Department.objects.filter(is_active=True)
        if self.has_role(Role.ADMIN, Role.HR):
            return queryset
        if self.has_role(Role.VIEWER):
            return queryset.none()
        return queryset.filter(
            pk__in=self.department_accesses.filter(level=AccessLevel.EDIT).values("department_id")
        )


class AccessLevel(models.TextChoices):
    VIEW = "view", "Просмотр"
    EDIT = "edit", "Редактирование"


class DepartmentAccess(models.Model):
    """Доступ пользователя к графикам отделения: только просмотр или редактирование."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="department_accesses",
        verbose_name="Пользователь",
    )
    department = models.ForeignKey(
        "core.Department",
        on_delete=models.CASCADE,
        related_name="accesses",
        verbose_name="Отделение",
    )
    level = models.CharField(
        "Уровень доступа", max_length=4, choices=AccessLevel.choices, default=AccessLevel.VIEW
    )

    class Meta:
        verbose_name = "доступ к отделению"
        verbose_name_plural = "доступ к отделениям"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "department"), name="uniq_access_user_department"
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.department} ({self.get_level_display()})"
