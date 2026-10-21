from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.schedule.models import ShiftLengthRule, Specialty


class SpecialtyRuleTests(TestCase):
    def setUp(self):
        self.uzd = Specialty.objects.create(name="Врач УЗД")
        # неполная ставка: не более 5,5 часа; полная и выше: не менее 5,6 часа
        self.part = ShiftLengthRule.objects.create(
            specialty=self.uzd, rate_from=Decimal("0"), rate_to=Decimal("1"), max_hours=Decimal("5.5")
        )
        self.full = ShiftLengthRule.objects.create(
            specialty=self.uzd, rate_from=Decimal("1"), min_hours=Decimal("5.6")
        )

    def test_rule_for_rate_picks_by_interval(self):
        self.assertEqual(self.uzd.rule_for_rate(Decimal("0.75")), self.part)
        self.assertEqual(self.uzd.rule_for_rate(Decimal("1")), self.full)
        self.assertEqual(self.uzd.rule_for_rate(Decimal("1.25")), self.full)

    def test_no_rule_returns_none(self):
        other = Specialty.objects.create(name="Хирург")
        self.assertIsNone(other.rule_for_rate(Decimal("1")))

    def test_rule_clean_rejects_min_above_max(self):
        rule = ShiftLengthRule(
            specialty=self.uzd, rate_from=Decimal("0"), min_hours=Decimal("6"), max_hours=Decimal("5")
        )
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_rule_clean_rejects_empty_bounds(self):
        rule = ShiftLengthRule(specialty=self.uzd, rate_from=Decimal("0"))
        with self.assertRaises(ValidationError):
            rule.full_clean()
