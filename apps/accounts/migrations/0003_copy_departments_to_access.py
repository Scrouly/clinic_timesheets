from django.db import migrations


def copy_departments(apps, schema_editor):
    """Переносит старые связи «пользователь — отделение» в таблицу доступа с уровнем «редактирование»."""
    User = apps.get_model("accounts", "User")
    DepartmentAccess = apps.get_model("accounts", "DepartmentAccess")
    for link in User.departments.through.objects.all():
        DepartmentAccess.objects.get_or_create(
            user_id=link.user_id,
            department_id=link.department_id,
            defaults={"level": "edit"},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_departmentaccess"),
    ]

    operations = [
        migrations.RunPython(copy_departments, migrations.RunPython.noop),
    ]
