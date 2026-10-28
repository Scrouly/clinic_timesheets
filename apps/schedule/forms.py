from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from . import rows
from .models import Assignment, Cabinet, Doctor, Schedule, Shift, Specialty, TimeKind


class ShiftForm(forms.ModelForm):
    """Форма смены. График определяется сам: по отделению врача и месяцу даты."""

    class Meta:
        model = Shift
        fields = ("assignment", "date", "kind", "start", "end", "cabinet")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "start": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        editable = user.editable_departments()
        current = self.instance if self.instance.pk else None

        assignments = Q(department__in=editable, is_active=True)
        kinds = Q(is_active=True)
        cabinets = Q(is_active=True)
        if current is not None:  # уже выбранное значение остаётся доступным, даже если его отключили
            assignments |= Q(pk=current.assignment_id)
            kinds |= Q(pk=current.kind_id)
            if current.cabinet_id:
                cabinets |= Q(pk=current.cabinet_id)

        self.fields["assignment"].queryset = (
            Assignment.objects.filter(assignments)
            .select_related("doctor", "specialty", "department")
            .order_by("department__sort_order", "doctor__last_name", "doctor__first_name", "specialty__name")
        )
        self.fields["kind"].queryset = TimeKind.objects.filter(kinds)
        self.fields["cabinet"].queryset = Cabinet.objects.filter(cabinets)

    def clean(self):
        cleaned = super().clean()
        assignment, day = cleaned.get("assignment"), cleaned.get("date")
        if assignment and day:
            try:
                self.instance.schedule = Schedule.objects.get(
                    department_id=assignment.department_id, year=day.year, month=day.month
                )
            except Schedule.DoesNotExist:
                raise ValidationError(
                    f"Для отделения «{assignment.department}» нет графика на {day:%m.%Y}. "
                    "Попросите кадровика или администратора создать его."
                )
        return cleaned


def _rate_field():
    return forms.DecimalField(
        label="Ставка",
        min_value=rows.MIN_RATE,
        max_value=rows.MAX_RATE,
        max_digits=3,
        decimal_places=2,
        localize=True,  # принимает и 0,75, и 0.75
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
    )


class RowCreateForm(forms.Form):
    """Добавление врача в график. Выбирать можно только тех, кто уже есть в справочнике."""

    doctor = forms.ModelChoiceField(Doctor.objects.all(), label="Врач", empty_label="Выберите врача")
    specialty = forms.ModelChoiceField(
        Specialty.objects.filter(is_active=True), label="Профессия", empty_label="Выберите профессию"
    )
    rate = _rate_field()
    position = forms.IntegerField(required=False, min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, schedule, **kwargs):
        super().__init__(*args, **kwargs)
        self.schedule = schedule
        self.fields["rate"].initial = "1"

    def save(self):
        """Создаёт строку; повтор врача и профессии становится ошибкой формы."""
        data = self.cleaned_data
        try:
            return rows.add_row(self.schedule, data["doctor"], data["specialty"], data["rate"], data["position"])
        except rows.RowError as error:
            self.add_error(None, error.message)
            return None


class RowEditForm(forms.Form):
    """Ставка и профессия строки только в этом месяце."""

    specialty = forms.ModelChoiceField(Specialty.objects.filter(is_active=True), label="Профессия")
    rate = _rate_field()

    def __init__(self, *args, row, **kwargs):
        super().__init__(*args, **kwargs)
        self.row = row
        self.fields["specialty"].initial = row.assignment.specialty_id
        self.fields["rate"].initial = format(row.rate.normalize(), "f")
        if not row.assignment.specialty.is_active:  # текущая профессия остаётся в списке, даже если её выключили
            self.fields["specialty"].queryset = Specialty.objects.filter(
                Q(is_active=True) | Q(pk=row.assignment.specialty_id)
            )

    def save(self):
        try:
            return rows.update_row(self.row, rate=self.cleaned_data["rate"], specialty=self.cleaned_data["specialty"])
        except rows.RowError as error:
            self.add_error(None, error.message)
            return None


class RowRemoveForm(forms.Form):
    """Подтверждение удаления строки: нужно число смен, которые вместе с ней пропадут."""

    confirm = forms.IntegerField(required=False, min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, row, **kwargs):
        super().__init__(*args, **kwargs)
        self.row = row
        self.shift_count = Shift.objects.filter(schedule=row.schedule, assignment=row.assignment).count()
        self.fields["confirm"].initial = self.shift_count

    def save(self):
        try:
            return rows.remove_row(self.row, confirm=self.cleaned_data.get("confirm") or 0)
        except rows.ConfirmRequired:
            self.data = self.data.copy()
            self.data["confirm"] = str(self.shift_count)  # в повторной форме уже стоит верное число
            self.add_error(
                None,
                f"Подтвердите удаление: вместе со строкой пропадёт смен за месяц: {self.shift_count}.",
            )
            return None
