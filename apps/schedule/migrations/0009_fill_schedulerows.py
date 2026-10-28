from django.db import migrations
from django.db.models import Q


def fill_rows(apps, schema_editor):
    """Строки для уже существующих графиков: действующие врачи отделения и те, у кого есть смены."""
    Schedule = apps.get_model("schedule", "Schedule")
    Assignment = apps.get_model("schedule", "Assignment")
    ScheduleRow = apps.get_model("schedule", "ScheduleRow")
    for schedule in Schedule.objects.all():
        assignments = (
            Assignment.objects.filter(department_id=schedule.department_id)
            .filter(Q(is_active=True) | Q(shifts__schedule_id=schedule.pk))
            .select_related("doctor", "specialty")
            .distinct()
        )
        ordered = sorted(
            assignments,
            key=lambda a: (a.doctor.last_name, a.doctor.first_name, a.doctor.patronymic, a.specialty.name),
        )
        for position, assignment in enumerate(ordered, start=1):
            ScheduleRow.objects.get_or_create(
                schedule_id=schedule.pk,
                assignment_id=assignment.pk,
                defaults={"rate": assignment.rate, "sort_order": position},
            )


class Migration(migrations.Migration):
    dependencies = [("schedule", "0008_schedulerow")]
    operations = [migrations.RunPython(fill_rows, migrations.RunPython.noop)]
