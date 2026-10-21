from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.schedule.models import TimeKind


class TimeKindTests(TestCase):
    def test_defaults(self):
        kind = TimeKind.objects.create(name="Отпуск", short_label="ОТП")
        self.assertFalse(kind.is_working)
        self.assertTrue(kind.is_active)
        self.assertEqual(kind.code_1c, "")
        self.assertEqual(str(kind), "Отпуск")

    def test_name_is_unique(self):
        TimeKind.objects.create(name="Отпуск", short_label="ОТП")
        with self.assertRaises(IntegrityError), transaction.atomic():
            TimeKind.objects.create(name="Отпуск", short_label="О")
