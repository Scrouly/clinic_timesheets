from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Assignment, Cabinet, Schedule, Shift, TimeKind


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
