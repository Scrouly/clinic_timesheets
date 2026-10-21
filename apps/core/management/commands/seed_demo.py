from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.core.models import Department

DEPARTMENTS = (
    ("Диагностическое отделение", "Диагностическое"),
    ("Консультативное отделение", "Консультативное"),
    ("Консультативное отделение №2", "Консультативное №2"),
    ("Хирургическое отделение", "Хирургическое"),
    ("МИБС (МРТ)", "МИБС"),
)

# логин, фамилия, имя, отчество, роль, номера отделений (с нуля)
USERS = (
    ("admin", "Волков", "Сергей", "Андреевич", Role.ADMIN, ()),
    ("hr", "Крылова", "Анна", "Игоревна", Role.HR, ()),
    ("head_diag", "Зуев", "Дмитрий", "Павлович", Role.HEAD, (0,)),
    ("head_cons", "Громова", "Татьяна", "Николаевна", Role.HEAD, (1, 2)),
    ("viewer", "Ефимов", "Олег", "Леонидович", Role.VIEWER, ()),
)


class Command(BaseCommand):
    help = "Создаёт отделения и тестовых пользователей для проверки интерфейса (только для разработки)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo-pass-2026")
        parser.add_argument("--force", action="store_true", help="разрешить запуск при DEBUG=False")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Команда только для разработки. Для рабочей базы она не нужна.")

        departments = []
        for index, (name, short) in enumerate(DEPARTMENTS):
            department, _ = Department.objects.get_or_create(
                name=name, defaults={"short_name": short, "sort_order": index}
            )
            departments.append(department)

        for username, last, first, patronymic, role, dept_indexes in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "last_name": last,
                    "first_name": first,
                    "patronymic": patronymic,
                    "role": role,
                    "is_staff": role == Role.ADMIN,
                    "is_superuser": role == Role.ADMIN,
                },
            )
            if created:
                user.set_password(options["password"])
                user.save()
            user.departments.set([departments[i] for i in dept_indexes])
            self.stdout.write(f"{'создан ' if created else 'уже есть'} {username} ({role})")

        self.stdout.write(self.style.SUCCESS(f"Готово. Пароль новых пользователей: {options['password']}"))
