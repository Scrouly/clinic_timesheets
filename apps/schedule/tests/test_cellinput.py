from datetime import time

from django.test import TestCase

from apps.schedule.cellinput import CellError, ParsedEntry, format_cell, parse_cell
from apps.schedule.models import Cabinet, TimeKind

from .helpers import ScheduleTestMixin


class CellInputBase(ScheduleTestMixin):
    def setUp(self):
        self.setUpData()
        self.cab_a = Cabinet.objects.create(name="301А")
        self.uzi = Cabinet.objects.create(name="УЗИ-1")
        self.sick = TimeKind.objects.create(name="Больничный", short_label="б/л")
        self.cabinets = list(Cabinet.objects.all())
        self.kinds = list(TimeKind.objects.all())

    def parse(self, raw, default=None):
        return parse_cell(raw, self.cabinets, self.kinds, default)


class ParseTimeTests(CellInputBase, TestCase):
    def test_time_with_cabinet(self):
        self.assertEqual(self.parse("8-14:40 301"), [ParsedEntry(self.work, time(8, 0), time(14, 40), self.cab1)])

    def test_time_separators_are_free(self):
        expected = [ParsedEntry(self.work, time(8, 30), time(14, 0), self.cab1)]
        variants = (
            "8.30-14 301", "8:30-14 301", "830-1400 301", "08:30–14:00 301", "8:30 — 14:00 301", "8:30-14:00   301",
        )
        for raw in variants:
            self.assertEqual(self.parse(raw), expected, raw)

    def test_hours_only(self):
        self.assertEqual(self.parse("9-15 301"), [ParsedEntry(self.work, time(9, 0), time(15, 0), self.cab1)])

    def test_two_shifts_in_a_day(self):
        for raw in ("8-12 301; 14-18 302", "8-12 301 + 14-18 302", "8-12 301;14-18 302;"):
            self.assertEqual(
                self.parse(raw),
                [
                    ParsedEntry(self.work, time(8, 0), time(12, 0), self.cab1),
                    ParsedEntry(self.work, time(14, 0), time(18, 0), self.cab2),
                ],
                raw,
            )

    def test_empty_clears_the_day(self):
        for raw in ("", "   ", None, ";"):
            self.assertEqual(self.parse(raw), [], repr(raw))

    def test_invalid_time_is_explained(self):
        for raw in ("8-", "abc", "8", "25-26 301", "8:75-14 301", "14-8 301", "8-8 301"):
            result = self.parse(raw)
            self.assertIsInstance(result, CellError, raw)
            self.assertTrue(result.message, raw)

    def test_end_must_be_after_start(self):
        self.assertIn("позже начала", self.parse("14-8 301").message)

    def test_error_in_one_part_rejects_the_whole_cell(self):
        self.assertIsInstance(self.parse("8-12 301; 14-"), CellError)


class ParseKindTests(CellInputBase, TestCase):
    def test_absence_by_label_or_name_in_any_case(self):
        self.assertEqual(self.parse("отп"), [ParsedEntry(self.vacation)])
        self.assertEqual(self.parse("ОТП"), [ParsedEntry(self.vacation)])
        self.assertEqual(self.parse("Отпуск"), [ParsedEntry(self.vacation)])
        self.assertEqual(self.parse("б/л"), [ParsedEntry(self.sick)])

    def test_unknown_label_is_an_error(self):
        self.assertIsInstance(self.parse("ком"), CellError)

    def test_inactive_kinds_are_ignored_by_the_caller(self):
        kinds = [k for k in self.kinds if k.pk != self.sick.pk]
        self.assertIsInstance(parse_cell("б/л", self.cabinets, kinds), CellError)

    def test_missing_working_kind(self):
        kinds = [k for k in self.kinds if not k.is_working]
        self.assertIn("рабочее время", parse_cell("8-14 301", self.cabinets, kinds).message)


class ParseCabinetTests(CellInputBase, TestCase):
    def test_exact_match_beats_prefix(self):
        self.assertEqual(self.parse("8-14 301")[0].cabinet, self.cab1)  # есть и «301», и «301А»

    def test_prefix_when_unique(self):
        self.assertEqual(self.parse("8-14 301а")[0].cabinet, self.cab_a)
        self.assertEqual(self.parse("8-14 уз")[0].cabinet, self.uzi)

    def test_case_spaces_and_hyphens_are_ignored(self):
        for raw in ("8-14 узи1", "8-14 УЗИ-1", "8-14 узи 1", "8-14 Узи-1"):
            self.assertEqual(self.parse(raw)[0].cabinet, self.uzi, raw)

    def test_ambiguous_prefix_lists_the_variants(self):
        result = self.parse("8-14 30")
        self.assertIsInstance(result, CellError)
        self.assertIn("301", result.message)
        self.assertIn("302", result.message)

    def test_unknown_cabinet(self):
        self.assertIn("Не нашёл кабинет", self.parse("8-14 999").message)

    def test_default_cabinet_value_or_function(self):
        self.assertEqual(self.parse("9-15", self.cab2)[0].cabinet, self.cab2)
        self.assertEqual(self.parse("9-15", lambda: self.cab2)[0].cabinet, self.cab2)

    def test_default_cabinet_is_not_requested_when_the_text_has_one(self):
        def boom():
            raise AssertionError("кабинет по умолчанию не нужен")

        self.assertEqual(self.parse("9-15 302", boom)[0].cabinet, self.cab2)

    def test_no_cabinet_and_no_default_is_an_error(self):
        self.assertIn("Укажите кабинет", self.parse("9-15").message)

    def test_cabinet_may_follow_the_middle_dot_of_the_canonical_form(self):
        self.assertEqual(self.parse("08:00–14:40 · 301")[0].cabinet, self.cab1)


class FormatTests(CellInputBase, TestCase):
    def test_canonical_form(self):
        entries = [ParsedEntry(self.work, time(8, 0), time(14, 40), self.cab1)]
        self.assertEqual(format_cell(entries), "08:00–14:40 · 301")

    def test_absence_and_order(self):
        entries = [
            ParsedEntry(self.work, time(14, 0), time(18, 0), self.cab2),
            ParsedEntry(self.work, time(8, 0), time(12, 0), self.cab1),
        ]
        self.assertEqual(format_cell(entries), "08:00–12:00 · 301; 14:00–18:00 · 302")
        self.assertEqual(format_cell([ParsedEntry(self.vacation)]), "ОТП")
        self.assertEqual(format_cell([]), "")

    def test_format_and_parse_are_inverse_on_many_values(self):
        cabinets = self.cabinets
        checked = 0
        for start_h in range(0, 23, 3):
            for start_m in (0, 5, 30, 59):
                for length in (30, 95, 360, 600):
                    total = start_h * 60 + start_m + length
                    if total >= 24 * 60:
                        continue
                    start, end = time(start_h, start_m), time(total // 60, total % 60)
                    for cabinet in cabinets:
                        entries = [ParsedEntry(self.work, start, end, cabinet)]
                        self.assertEqual(self.parse(format_cell(entries)), entries, format_cell(entries))
                        checked += 1
        self.assertGreater(checked, 300)

    def test_format_and_parse_are_inverse_for_several_entries(self):
        entries = [
            ParsedEntry(self.work, time(8, 0), time(12, 0), self.cab1),
            ParsedEntry(self.work, time(13, 0), time(17, 30), self.uzi),
        ]
        self.assertEqual(self.parse(format_cell(entries)), entries)
        for kind in (self.vacation, self.sick):
            self.assertEqual(self.parse(format_cell([ParsedEntry(kind)])), [ParsedEntry(kind)])
