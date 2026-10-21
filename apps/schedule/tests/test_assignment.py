from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import Department
from apps.schedule.models import Assignment, Doctor, ShiftLengthRule, Specialty


class DoctorTests(TestCase):
    def test_names(self):
        doctor = Doctor(last_name="Иванов", first_name="Иван", patronymic="Петрович")
        self.assertEqual(doctor.full_name, "Иванов Иван Петрович")
        self.assertEqual(doctor.short_name, "Иванов И.П.")

    def test_tab_number_unique_when_set(self):
        Doctor.objects.create(last_name="А", first_name="А", tab_number="101")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Doctor.objects.create(last_name="Б", first_name="Б", tab_number="101")
        Doctor.objects.create(last_name="В", first_name="В")
        Doctor.objects.create(last_name="Г", first_name="Г")  # без номера допустимо


class AssignmentTests(TestCase):
    def setUp(self):
        self.diag = Department.objects.create(name="Диагностическое отделение")
        self.cons = Department.objects.create(name="Консультативное отделение")
        self.uzd = Specialty.objects.create(name="Врач УЗД")
        self.surgeon = Specialty.objects.create(name="Хирург")
        self.doctor = Doctor.objects.create(last_name="Иванов", first_name="Иван")
        ShiftLengthRule.objects.create(
            specialty=self.uzd, rate_from=Decimal("0"), rate_to=Decimal("1"), max_hours=Decimal("5.5")
        )

    def make(self, **kwargs):
        defaults = dict(
            doctor=self.doctor, department=self.diag, specialty=self.uzd, rate=Decimal("0.75")
        )
        defaults.update(kwargs)
        return Assignment.objects.create(**defaults)

    def test_assignment_unique_per_doctor_department_specialty(self):
        self.make()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make()

    def test_doctor_in_two_departments_is_allowed(self):
        self.make()
        self.make(department=self.cons)
        self.assertEqual(self.doctor.assignments.count(), 2)

    def test_shift_limits_own_override_rule(self):
        assignment = self.make(min_shift_hours=Decimal("4"), max_shift_hours=Decimal("6"))
        self.assertEqual(assignment.shift_limits(), (Decimal("4"), Decimal("6")))

    def test_shift_limits_only_max_set_ignores_rule(self):
        assignment = self.make(max_shift_hours=Decimal("7"))
        self.assertEqual(assignment.shift_limits(), (None, Decimal("7")))

    def test_shift_limits_fall_back_to_rule(self):
        self.assertEqual(self.make().shift_limits(), (None, Decimal("5.5")))

    def test_shift_limits_without_rule(self):
        assignment = self.make(specialty=self.surgeon)
        self.assertEqual(assignment.shift_limits(), (None, None))
