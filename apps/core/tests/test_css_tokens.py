import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS_PATH = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(")


def _css():
    return CSS_PATH.read_text(encoding="utf-8")


def _root_block(css):
    start = css.index(":root {")
    end = css.index("\n}", start)
    return css[start:end]


class CssTokensTests(SimpleTestCase):
    def test_no_color_literals_outside_root(self):
        css = _css()
        root = _root_block(css)
        rest = css.replace(root, "")
        found = [
            (n, line.strip())
            for n, line in enumerate(rest.splitlines(), 1)
            if COLOR_LITERAL.search(line)
        ]
        self.assertEqual(found, [], "цвета нужно выносить в переменные :root")

    def test_all_used_vars_are_defined(self):
        css = _css()
        # переменные задаются в :root или на отдельных классах (например, --stripe у .is-*)
        defined = set(re.findall(r"(--[\w-]+)\s*:", css))
        used = set(re.findall(r"var\((--[\w-]+)", css))
        self.assertEqual(sorted(used - defined), [])


# --- палитра CityClinic ---------------------------------------------------

def _tokens():
    root = _root_block(_css())
    return {k: v.lower() for k, v in re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\b", root)}


def _lum(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)

STATUS_TOKENS = {
    "--st-composed-bg": "#cdeec8",
    "--st-composed-ink": "#1e5a1b",
    "--st-composed-bar": "#35b02b",
    "--st-entered-bg": "#b8d2e7",
    "--st-entered-ink": "#1d4568",
    "--st-entered-bar": "#5b8fb9",
    "--st-review-bg": "#bdecf1",
    "--st-review-ink": "#0c5560",
    "--st-review-bar": "#1fa3b4",
    "--st-changed-bg": "#f2c8ee",
    "--st-changed-ink": "#7a1d73",
    "--st-changed-bar": "#c23bb8",
    "--st-error-bg": "#f7c5bf",
    "--st-error-ink": "#8f1d14",
    "--st-error-bar": "#d93025",
    "--st-dayoff-bg": "#ecf7de",
    "--st-dayoff-ink": "#4a5d33",
    "--st-dayoff-bar": "#9cc46a",
    "--st-holiday-bg": "#ffdfec",
    "--st-holiday-ink": "#8a2650",
    "--st-holiday-bar": "#e08aae",
    "--st-draft-bg": "#e6ebe9",
    "--st-draft-ink": "#3a505a",
    "--st-draft-bar": "#9bb0a8",
    "--st-submitted-bg": "#fde8b3",
    "--st-submitted-ink": "#6e4b00",
    "--st-submitted-bar": "#e0a100",
    "--st-returned-bg": "#fcd5b6",
    "--st-returned-ink": "#8a3d00",
    "--st-returned-bar": "#e07a1a",
    "--st-approved-bg": "#11704a",
    "--st-approved-ink": "#ffffff",
    "--st-approved-bar": "#11704a",
    "--st-exported-bg": "#27466b",
    "--st-exported-ink": "#ffffff",
    "--st-exported-bar": "#27466b",
}

class PaletteTests(SimpleTestCase):
    def assertContrast(self, fg, bg, minimum):
        t = _tokens()
        ratio = contrast(t[fg], t[bg])
        self.assertGreaterEqual(ratio, minimum, f"{fg} на {bg}: {ratio:.2f} < {minimum}")

    def test_text_contrast(self):
        for fg in ("--ink", "--ink-2", "--ink-3"):
            for bg in ("--surface", "--paper", "--tint", "--surface-2"):
                self.assertContrast(fg, bg, 4.5)

    def test_brand_text_contrast(self):
        for bg in ("--surface", "--paper", "--tint"):
            self.assertContrast("--brand-text", bg, 4.5)
        for fg in ("--on-fill",):
            for bg in ("--brand-text", "--brand-strong", "--danger", "--danger-strong"):
                self.assertContrast(fg, bg, 4.5)

    def test_danger_and_warning_text_contrast(self):
        for fg in ("--danger", "--warn-ink"):
            self.assertContrast(fg, "--surface", 4.5)

    def test_menu_text_contrast(self):
        # светлое меню: обычный пункт, пункт при наведении и активный пункт
        self.assertContrast("--ink-2", "--surface", 4.5)
        self.assertContrast("--ink", "--tint", 4.5)
        self.assertContrast("--brand-text", "--tint", 4.5)

    def test_ui_parts_contrast(self):
        self.assertContrast("--focus", "--surface", 3.0)
        self.assertContrast("--brand", "--surface", 3.0)

    def test_brand_fill_not_used_for_text(self):
        css = _css()
        offenders = re.findall(r"(?<![-\w])color:\s*var\(--brand\)", css)
        self.assertEqual(offenders, [], "яркий --brand только для заливок, для текста --brand-text")

    def test_brand_colors_match_logo(self):
        t = _tokens()
        self.assertEqual(t["--brand"], "#0093ce")
        self.assertEqual(t["--brand-2"], "#a9dcf1")
        self.assertEqual(t["--ink"], "#000b45")

    def test_status_tokens_unchanged(self):
        t = _tokens()
        actual = {k: v for k, v in t.items() if k.startswith("--st-")}
        self.assertEqual(actual, STATUS_TOKENS)
