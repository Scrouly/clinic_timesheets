from datetime import date as date_type
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Max, Q


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


class Specialty(models.Model):
    """Профессия врача. От неё зависят правила длины смены."""

    name = models.CharField("Название", max_length=100, unique=True)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "профессия"
        verbose_name_plural = "профессии"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def rule_for_rate(self, rate):
        """Правило длины смены для ставки: rate_from <= ставка < rate_to (пустой rate_to — без верхней границы)."""
        # сортировка в Python: так работает и prefetch_related("length_rules") без запроса на каждый вызов
        for rule in sorted(self.length_rules.all(), key=lambda r: r.rate_from):
            if rule.rate_from <= rate and (rule.rate_to is None or rate < rule.rate_to):
                return rule
        return None


class ShiftLengthRule(models.Model):
    """Границы длины смены для профессии при ставке из диапазона."""

    specialty = models.ForeignKey(
        Specialty, on_delete=models.CASCADE, related_name="length_rules", verbose_name="Профессия"
    )
    rate_from = models.DecimalField("Ставка от (включительно)", max_digits=3, decimal_places=2, default=0)
    rate_to = models.DecimalField(
        "Ставка до (не включая)",
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Пусто — без верхней границы.",
    )
    min_hours = models.DecimalField("Не менее, часов", max_digits=4, decimal_places=2, null=True, blank=True)
    max_hours = models.DecimalField("Не более, часов", max_digits=4, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "правило длины смены"
        verbose_name_plural = "правила длины смены"
        ordering = ("rate_from",)

    def __str__(self):
        return f"{self.specialty}: от {self.rate_from}"

    def clean(self):
        if self.min_hours is None and self.max_hours is None:
            raise ValidationError("Укажите хотя бы одну границу: минимум или максимум.")
        if self.min_hours is not None and self.max_hours is not None and self.min_hours > self.max_hours:
            raise ValidationError("Минимум не может быть больше максимума.")


class Doctor(models.Model):
    """Человек. Его работа в отделениях описывается записями Assignment."""

    last_name = models.CharField("Фамилия", max_length=100)
    first_name = models.CharField("Имя", max_length=100)
    patronymic = models.CharField("Отчество", max_length=100, blank=True)
    tab_number = models.CharField(
        "Табельный номер", max_length=20, null=True, blank=True, unique=True
    )

    class Meta:
        verbose_name = "врач"
        verbose_name_plural = "врачи"
        ordering = ("last_name", "first_name", "patronymic")

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return " ".join(p for p in (self.last_name, self.first_name, self.patronymic) if p)

    @property
    def short_name(self):
        initials = "".join(f"{p[0]}." for p in (self.first_name, self.patronymic) if p)
        return f"{self.last_name} {initials}".strip()


class Assignment(models.Model):
    """Врач в отделении: профессия и ставка. У одного врача таких записей может быть несколько."""

    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="assignments", verbose_name="Врач"
    )
    department = models.ForeignKey(
        "core.Department", on_delete=models.PROTECT, related_name="assignments", verbose_name="Отделение"
    )
    specialty = models.ForeignKey(
        Specialty, on_delete=models.PROTECT, related_name="assignments", verbose_name="Профессия"
    )
    rate = models.DecimalField("Ставка", max_digits=3, decimal_places=2)
    min_shift_hours = models.DecimalField(
        "Своя длина смены: не менее, часов",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Если заполнена хотя бы одна своя граница, правило профессии не применяется.",
    )
    max_shift_hours = models.DecimalField(
        "Своя длина смены: не более, часов", max_digits=4, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "работа врача в отделении"
        verbose_name_plural = "работа врачей в отделениях"
        ordering = ("department", "doctor")
        constraints = [
            models.UniqueConstraint(
                fields=("doctor", "department", "specialty"), name="uniq_assignment_doctor_dept_specialty"
            ),
        ]

    def __str__(self):
        return f"{self.doctor.short_name}, {self.specialty}, {self.department.label} ({self.rate})"

    def shift_limits(self, rate=None):
        """(минимум, максимум) длины смены: свои границы главнее правила профессии.

        rate: ставка месяца из строки графика; без неё берётся ставка по умолчанию у Assignment.
        """
        if self.min_shift_hours is not None or self.max_shift_hours is not None:
            return (self.min_shift_hours, self.max_shift_hours)
        rule = self.specialty.rule_for_rate(self.rate if rate is None else rate)
        if rule is not None:
            return (rule.min_hours, rule.max_hours)
        return (None, None)


class TimeKind(models.Model):
    """Вид времени в графике: работа, отпуск, больничный, командировка и т. п."""

    name = models.CharField("Название", max_length=50, unique=True)
    short_label = models.CharField("Метка в ячейке", max_length=10)
    code_1c = models.CharField("Код для 1С", max_length=30, blank=True)
    is_working = models.BooleanField(
        "Рабочее время",
        default=False,
        help_text="Для рабочего времени обязательны начало, конец и кабинет.",
    )
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "вид времени"
        verbose_name_plural = "виды времени"
        ordering = ("name",)

    def __str__(self):
        return self.name


class ScheduleStatus(models.TextChoices):
    DRAFT = "draft", "Составляется"
    APPROVED = "approved", "Утверждён"


class Schedule(models.Model):
    """График отделения на месяц. Данные графика лежат в сменах Shift."""

    department = models.ForeignKey(
        "core.Department", on_delete=models.PROTECT, related_name="schedules", verbose_name="Отделение"
    )
    year = models.PositiveSmallIntegerField("Год")
    month = models.PositiveSmallIntegerField(
        "Месяц", validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    status = models.CharField(
        "Статус", max_length=10, choices=ScheduleStatus.choices, default=ScheduleStatus.DRAFT
    )
    approved_on = models.DateField("Дата утверждения", null=True, blank=True)

    class Meta:
        verbose_name = "график"
        verbose_name_plural = "графики"
        ordering = ("-year", "-month", "department")
        constraints = [
            models.UniqueConstraint(
                fields=("department", "year", "month"), name="uniq_schedule_department_month"
            ),
        ]

    def __str__(self):
        return f"{self.department} — {self.month:02d}.{self.year}"


class ScheduleRow(models.Model):
    """Строка графика: врач в отделении в конкретном месяце, со ставкой этого месяца.

    Состав строк принадлежит месяцу: врач, добавленный в октябре, не появляется в других месяцах,
    а изменённая ставка не меняет норму прошлых графиков.
    """

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="rows", verbose_name="График")
    assignment = models.ForeignKey(
        Assignment, on_delete=models.PROTECT, related_name="schedule_rows", verbose_name="Врач в отделении"
    )
    rate = models.DecimalField("Ставка в этом месяце", max_digits=3, decimal_places=2)
    sort_order = models.PositiveIntegerField("Порядок в графике", default=0)

    class Meta:
        verbose_name = "строка графика"
        verbose_name_plural = "строки графика"
        ordering = ("schedule", "sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("schedule", "assignment"), name="uniq_schedule_row_assignment"),
        ]

    def __str__(self):
        return f"{self.schedule}: {self.assignment.doctor.short_name} ({self.rate})"

    def clean(self):
        if self.assignment_id and self.schedule_id:
            if self.assignment.department_id != self.schedule.department_id:
                raise ValidationError({"assignment": "Врач работает не в отделении этого графика."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def ensure(cls, schedule, assignment):
        """Строка этого врача в графике; если её нет, создаётся в конце со ставкой по умолчанию."""
        row = cls.objects.filter(schedule=schedule, assignment=assignment).first()
        if row is not None:
            return row
        last = cls.objects.filter(schedule=schedule).aggregate(last=Max("sort_order"))["last"] or 0
        return cls.objects.create(schedule=schedule, assignment=assignment, rate=assignment.rate, sort_order=last + 1)


class Shift(models.Model):
    """Запись графика на один день. Единственный источник данных для обоих видов графика."""

    schedule = models.ForeignKey(
        Schedule, on_delete=models.CASCADE, related_name="shifts", verbose_name="График"
    )
    assignment = models.ForeignKey(
        Assignment, on_delete=models.PROTECT, related_name="shifts", verbose_name="Врач в отделении"
    )
    date = models.DateField("Дата")
    kind = models.ForeignKey(
        TimeKind, on_delete=models.PROTECT, related_name="shifts", verbose_name="Вид времени"
    )
    start = models.TimeField("Начало", null=True, blank=True)
    end = models.TimeField("Конец", null=True, blank=True)
    cabinet = models.ForeignKey(
        Cabinet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shifts",
        verbose_name="Кабинет",
    )

    class Meta:
        verbose_name = "смена"
        verbose_name_plural = "смены"
        ordering = ("date", "start")
        constraints = [
            models.CheckConstraint(
                condition=Q(start__isnull=True) | Q(end__isnull=True) | Q(end__gt=F("start")),
                name="shift_end_after_start",
            ),
        ]

    def __str__(self):
        if self.start and self.end:
            return f"{self.date:%d.%m.%Y} {self.start:%H:%M}–{self.end:%H:%M}"
        return f"{self.date:%d.%m.%Y} {self.kind}"

    @property
    def hours(self):
        """Длина рабочей смены в часах с точностью до сотых; для нерабочих видов 0."""
        if not (self.kind.is_working and self.start and self.end):
            return Decimal("0.00")
        delta = datetime.combine(date_type.min, self.end) - datetime.combine(date_type.min, self.start)
        hours = Decimal(int(delta.total_seconds())) / Decimal(3600)
        return hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def clean(self):
        errors = {}
        if self.assignment_id and self.schedule_id:
            if self.assignment.department_id != self.schedule.department_id:
                errors["assignment"] = "Врач работает не в отделении этого графика."
        if self.date and self.schedule_id:
            if (self.date.year, self.date.month) != (self.schedule.year, self.schedule.month):
                errors["date"] = "Дата не входит в месяц графика."
        if self.kind_id:
            if self.kind.is_working:
                required = (("start", self.start), ("end", self.end), ("cabinet", self.cabinet_id))
                for name, value in required:
                    if value is None:
                        errors[name] = "Обязательно для рабочей смены."
                if self.start is not None and self.end is not None and self.end <= self.start:
                    errors["end"] = (
                        "Конец смены должен быть позже начала. "
                        "Смена не может переходить через полночь."
                    )
            else:
                for name, value in (("start", self.start), ("end", self.end), ("cabinet", self.cabinet_id)):
                    if value is not None:
                        errors[name] = "Для этого вида времени не указывается."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            ScheduleRow.ensure(self.schedule, self.assignment)  # смена всегда лежит в строке графика


class DayKind(models.TextChoices):
    WORKDAY = "workday", "Рабочий"
    WEEKEND = "weekend", "Выходной"
    HOLIDAY = "holiday", "Праздничный"
    SHORTENED = "shortened", "Сокращённый"


class CalendarDay(models.Model):
    """Отметка дня производственного календаря (для окраски выходных и праздников в сетке)."""

    date = models.DateField("Дата", unique=True)
    kind = models.CharField("Вид дня", max_length=10, choices=DayKind.choices)

    class Meta:
        verbose_name = "день календаря"
        verbose_name_plural = "производственный календарь"
        ordering = ("date",)

    def __str__(self):
        return f"{self.date:%d.%m.%Y} — {self.get_kind_display()}"


class MonthNorm(models.Model):
    """Норма часов за месяц на полную ставку (из официального календаря)."""

    year = models.PositiveSmallIntegerField("Год")
    month = models.PositiveSmallIntegerField(
        "Месяц", validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    hours = models.DecimalField("Часов на полную ставку", max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = "норма месяца"
        verbose_name_plural = "нормы месяцев"
        ordering = ("-year", "-month")
        constraints = [
            models.UniqueConstraint(fields=("year", "month"), name="uniq_month_norm_year_month"),
        ]

    def __str__(self):
        return f"{self.month:02d}.{self.year}: {self.hours} ч"


class SpecialtyMonthNorm(models.Model):
    """Собственная норма профессии на месяц; главнее общей нормы месяца."""

    specialty = models.ForeignKey(
        Specialty, on_delete=models.CASCADE, related_name="month_norms", verbose_name="Профессия"
    )
    year = models.PositiveSmallIntegerField("Год")
    month = models.PositiveSmallIntegerField(
        "Месяц", validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    hours = models.DecimalField("Часов на полную ставку", max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = "норма профессии на месяц"
        verbose_name_plural = "нормы профессий на месяц"
        ordering = ("-year", "-month", "specialty")
        constraints = [
            models.UniqueConstraint(
                fields=("specialty", "year", "month"), name="uniq_specialty_month_norm"
            ),
        ]

    def __str__(self):
        return f"{self.specialty}, {self.month:02d}.{self.year}: {self.hours} ч"
