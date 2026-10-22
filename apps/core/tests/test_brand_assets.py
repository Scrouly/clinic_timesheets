import re
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase

BRAND_DIR = Path(settings.BASE_DIR) / "static" / "img" / "brand"
BRAND_COLORS = {"#0093CE", "#A9DCF1"}
SVG_FILES = ("logo.svg", "logo-mark.svg")
ALL_FILES = SVG_FILES + ("logo.png", "favicon-32.png", "apple-touch-icon.png")


def _read(name):
    return (BRAND_DIR / name).read_text(encoding="utf-8")


class BrandAssetsTests(SimpleTestCase):
    def test_brand_files_exist(self):
        for name in ALL_FILES:
            self.assertTrue((BRAND_DIR / name).is_file(), name)

    def test_svg_uses_only_brand_colors(self):
        for name in SVG_FILES:
            fills = {f.upper() for f in re.findall(r'fill="(#[0-9A-Fa-f]{6})"', _read(name))}
            self.assertTrue(fills, name)
            self.assertLessEqual(fills, BRAND_COLORS, name)

    def test_svg_has_label_and_viewbox(self):
        for name in SVG_FILES:
            text = _read(name)
            self.assertIn('aria-label="CityClinic"', text, name)
            self.assertRegex(text, r'viewBox="[-\d.]+ [-\d.]+ [\d.]+ [\d.]+"', name)

    def test_mark_viewbox_is_square(self):
        box = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', _read("logo-mark.svg"))
        self.assertEqual(box.group(1), box.group(2))

    def test_head_links_brand_icons(self):
        html = render_to_string("partials/_head.html")
        self.assertIn("img/brand/logo-mark.svg", html)
        self.assertIn("img/brand/favicon-32.png", html)
        self.assertIn("img/brand/apple-touch-icon.png", html)
