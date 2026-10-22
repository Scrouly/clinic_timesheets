import calendar
from datetime import date, time
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import AccessLevel, DepartmentAccess, Role, User
from apps.core.models import Department
from apps.schedule.models import (
    Assignment,
    Cabinet,
    Doctor,
    MonthNorm,
    Schedule,
    Shift,
    ShiftLengthRule,
    Specialty,
    TimeKind,
)

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

CABINETS = ("115", "117", "201", "301", "УЗИ-1")

# вид времени: название, метка в ячейке, рабочее ли
TIME_KINDS = (
    ("Работа", "Р", True),
    ("Отпуск", "ОТП", False),
    ("Больничный", "Б/Л", False),
    ("Командировка", "КОМ", False),
)

# фамилия, имя, отчество, номер отделения (с нуля), профессия, ставка, кабинет, начало, конец,
# рабочие дни недели (0 — понедельник), сколько первых рабочих дней месяца в отпуске
STAFF = (
    ("Орлов", "Андрей", "Петрович", 3, "Хирург", "1.00", "301", (8, 0), (14, 40), (0, 1, 2, 3, 4), 0),
    ("Соколова", "Елена", "Викторовна", 1, "Эндокринолог", "0.75", "115", (9, 0), (14, 0), (0, 2, 4), 3),
    ("Мартынов", "Игорь", "Дмитриевич", 2, "Невролог", "1.00", "117", (8, 0), (14, 30), (0, 1, 2, 3, 4), 0),
    # в 117 кабинете Лаптева по вторникам и четвергам пересекается с Мартыновым: пример ошибки в графике
    ("Лаптева", "Ольга", "Николаевна", 2, "Кардиолог", "0.25", "117", (13, 0), (17, 0), (1, 3), 0),
    ("Белов", "Роман", "Сергеевич", 1, "Уролог", "0.50", "201", (15, 0), (20, 0), (0, 1, 2), 0),
    ("Зайцева", "Наталья", "Кирилловна", 1, "Акушер-гинеколог", "0.50", "201", (14, 0), (19, 0), (2, 3, 4), 0),
    ("Князев", "Павел", "Олегович", 0, "Врач УЗД", "0.75", "УЗИ-1", (9, 0), (14, 0), (0, 1, 2, 3, 4), 0),
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
            for index in dept_indexes:
                DepartmentAccess.objects.update_or_create(
                    user=user, department=departments[index], defaults={"level": AccessLevel.EDIT}
                )
            self.stdout.write(f"{'создан ' if created else 'уже есть'} {username} ({role})")

        self.seed_schedule(departments)
        self.stdout.write(self.style.SUCCESS(f"Готово. Пароль новых пользователей: {options['password']}"))

    def seed_schedule(self, departments):
        """Выдуманные кабинеты, врачи и график на текущий месяц (повторный запуск ничего не дублирует)."""
        today = timezone.localdate()
        year, month = today.year, today.month
        last_day = calendar.monthrange(year, month)[1]

        kinds = {}
        for name, label, is_working in TIME_KINDS:
            kinds[name], _ = TimeKind.objects.get_or_create(
                name=name, defaults={"short_label": label, "is_working": is_working}
            )
        cabinets = {
            name: Cabinet.objects.get_or_create(name=name, defaults={"sort_order": index})[0]
            for index, name in enumerate(CABINETS)
        }

        uzd, _ = Specialty.objects.get_or_create(name="Врач УЗД")
        ShiftLengthRule.objects.get_or_create(
            specialty=uzd,
            rate_from=Decimal("0"),
            defaults={"rate_to": Decimal("1"), "max_hours": Decimal("5.5")},
        )
        ShiftLengthRule.objects.get_or_create(
            specialty=uzd, rate_from=Decimal("1"), defaults={"min_hours": Decimal("5.6")}
        )

        workdays = sum(1 for number in range(1, last_day + 1) if date(year, month, number).weekday() < 5)
        MonthNorm.objects.get_or_create(
            year=year, month=month, defaults={"hours": Decimal(8 * workdays)}
        )

        for last, first, patronymic, dept_index, profession, rate, cabinet, start, end, week, vacation in STAFF:
            doctor, _ = Doctor.objects.get_or_create(
                last_name=last, first_name=first, patronymic=patronymic
            )
            specialty, _ = Specialty.objects.get_or_create(name=profession)
            department = departments[dept_index]
            assignment, _ = Assignment.objects.get_or_create(
                doctor=doctor,
                department=department,
                specialty=specialty,
                defaults={"rate": Decimal(rate)},
            )
            schedule, _ = Schedule.objects.get_or_create(department=department, year=year, month=month)
            vacation_left = vacation
            for number in range(1, last_day + 1):
                day = date(year, month, number)
                if day.weekday() not in week:
                    continue
                if vacation_left > 0:
                    vacation_left -= 1
                    Shift.objects.get_or_create(
                        schedule=schedule, assignment=assignment, date=day, kind=kinds["Отпуск"],
                        start=None, end=None, cabinet=None,
                    )
                    continue
                Shift.objects.get_or_create(
                    schedule=schedule, assignment=assignment, date=day, kind=kinds["Работа"],
                    start=time(*start), end=time(*end), cabinet=cabinets[cabinet],
                )
        self.stdout.write(f"график на {month:02d}.{year}: врачей {len(STAFF)}, смен {Shift.objects.count()}")
