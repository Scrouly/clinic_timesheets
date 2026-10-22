from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.schedule.models import CalendarDay, DayKind, MonthNorm, Specialty, SpecialtyMonthNorm


class CalendarModelsTests(TestCase):
    def test_calendar_day_date_unique(self):
        CalendarDay.objects.create(date=date(2026, 1, 1), kind=DayKind.HOLIDAY)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CalendarDay.objects.create(date=date(2026, 1, 1), kind=DayKind.WEEKEND)

    def test_month_norm_unique_per_month(self):
        MonthNorm.objects.create(year=2026, month=1, hours=Decimal("145.3"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            MonthNorm.objects.create(year=2026, month=1, hours=Decimal("150"))

    def test_specialty_month_norm_unique(self):
        uzd = Specialty.objects.create(name="Врач УЗД")
        SpecialtyMonthNorm.objects.create(specialty=uzd, year=2026, month=1, hours=Decimal("132"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpecialtyMonthNorm.objects.create(specialty=uzd, year=2026, month=1, hours=Decimal("130"))

    def test_month_validators(self):
        uzd = Specialty.objects.create(name="Врач УЗД")
        for month in (0, 13):
            with self.assertRaises(ValidationError, msg=month):
                MonthNorm(year=2026, month=month, hours=Decimal("145.3")).full_clean()
            with self.assertRaises(ValidationError, msg=month):
                SpecialtyMonthNorm(
                    specialty=uzd, year=2026, month=month, hours=Decimal("132")
                ).full_clean()
