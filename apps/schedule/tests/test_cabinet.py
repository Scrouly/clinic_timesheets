from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.schedule.models import Cabinet


class CabinetTests(TestCase):
    def test_defaults(self):
        cabinet = Cabinet.objects.create(name="301")
        self.assertFalse(cabinet.is_shared)
        self.assertTrue(cabinet.in_cabinet_schedule)
        self.assertTrue(cabinet.is_active)
        self.assertEqual(cabinet.sort_order, 0)
        self.assertEqual(str(cabinet), "301")

    def test_name_is_unique(self):
        Cabinet.objects.create(name="301")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cabinet.objects.create(name="301")

    def test_ordering_by_sort_order_then_name(self):
        b = Cabinet.objects.create(name="B", sort_order=1)
        a2 = Cabinet.objects.create(name="A", sort_order=2)
        a1 = Cabinet.objects.create(name="A1", sort_order=1)
        self.assertEqual(list(Cabinet.objects.all()), [a1, b, a2])
