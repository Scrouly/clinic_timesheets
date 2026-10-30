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
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

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


class StatusAndLayoutRulesTests(SimpleTestCase):
    def test_status_badges_are_readable(self):
        t = _tokens()
        names = sorted({k[5:-3] for k in t if k.startswith("--st-") and k.endswith("-bg")})
        self.assertTrue(names)
        for name in names:
            ratio = contrast(t[f"--st-{name}-ink"], t[f"--st-{name}-bg"])
            self.assertGreaterEqual(ratio, 4.5, f"статус {name}: {ratio:.2f}")

    def test_reduced_motion_is_respected(self):
        self.assertIn("prefers-reduced-motion: reduce", _css())

    def test_phone_breakpoint_exists(self):
        self.assertIn("@media (max-width: 40rem)", _css())

    def test_print_hides_panel_and_add_links(self):
        css = _css()
        start = css.index("@media print")
        printing = css[start:css.index("\n}\n", start)]
        self.assertIn(".side-panel", printing)
        self.assertIn(".cell__add", printing)



FIELD_SELECTOR = (
    '.field input[type="text"], .field input[type="password"], .field input[type="email"],\n'
    '.field input[type="number"], .field input[type="date"], .field input[type="time"],\n'
    ".field select, .field textarea"
)


def _rules(css):
    """Плоский список (селектор, тело) для правил без вложенности."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}@][^{}]*)\{([^{}]*)\}", css)]


def _strip_blocks(css, header):
    """Убирает из css блоки вида `@media ... { ... }` с заданным заголовком (с вложенными скобками)."""
    out, i = [], 0
    while True:
        start = css.find(header, i)
        if start == -1:
            out.append(css[i:])
            break
        out.append(css[i:start])
        depth, j = 0, css.index("{", start)
        while True:
            depth += css[j] == "{"
            depth -= css[j] == "}"
            j += 1
            if depth == 0:
                break
        i = j
    return "".join(out)


class AuditFixesTests(SimpleTestCase):
    def rule(self, selector):
        for sel, body in _rules(_css()):
            if sel == selector:
                return body
        self.fail(f"нет правила {selector}")

    def test_sticky_grids_reserve_scroll_padding(self):
        self.assertIn("scroll-padding-inline-start", self.rule(".grid-wrap"))
        self.assertIn("scroll-padding-block-start", self.rule(".grid-wrap"))
        self.assertIn("scroll-padding-block-start", self.rule(".grid-wrap--by-day"))
        self.assertIn("scroll-padding-inline-end", self.rule(".grid-wrap--sums"))

    def test_field_focus_keeps_a_forced_colors_outline(self):
        css = _css()
        offenders = [sel for sel, body in _rules(css) if re.search(r"outline:\s*none", body)]
        self.assertEqual(offenders, [".page:focus"])
        focus = self.rule(".field input:focus, .field select:focus, .field textarea:focus")
        self.assertIn("outline: 2px solid transparent", focus)

    def test_field_border_is_visible(self):
        t = _tokens()
        for bg in ("--surface", "--paper"):
            self.assertGreaterEqual(contrast(t["--field-border"], t[bg]), 3.0, bg)
        body = self.rule(FIELD_SELECTOR)
        self.assertIn("var(--field-border)", body)

    def test_error_cell_cabinet_text_is_readable(self):
        t = _tokens()
        self.assertGreaterEqual(contrast(t["--st-error-ink"], t["--st-error-bg"]), 4.5)
        self.assertIn("var(--st-error-ink)", self.rule(".cell--error .cell__cab"))

    def test_fills_use_fill_tokens(self):
        t = _tokens()
        offenders = re.findall(r"background:[^;{}]*var\(--(?:brand-text|ink|ink-2|ink-3)\)", _css())
        self.assertEqual(offenders, [])
        for fill in ("--accent-solid", "--accent-solid-strong", "--surface-inverse"):
            self.assertGreaterEqual(contrast(t["--on-fill"], t[fill]), 4.5, fill)

    def test_focus_color_is_only_for_focus(self):
        for selector, body in _rules(_css()):
            if "var(--focus)" in body:
                self.assertIn("focus", selector, selector)

    def test_hover_only_inside_hover_media(self):
        css = _strip_blocks(_css(), "@media (hover: hover)")
        self.assertNotIn(":hover", css)

    def test_touch_shows_add_control(self):
        css = _css()
        start = css.index("@media (hover: none)")
        self.assertIn(".cell__add", css[start:css.index("\n}", start)])

    def test_font_sizes_use_the_scale(self):
        css = _css()
        root = _root_block(css)
        outside = css.replace(root, "")
        self.assertEqual(re.findall(r"font-size:\s*[\d.]+(?:rem|px)", outside), [])
        scale = set(re.findall(r"(--text-[\w]+):\s*[\d.]+rem", root))
        self.assertLessEqual(len(scale), 7)
        self.assertGreaterEqual(len(scale), 5)

    def test_no_global_feature_tag_for_digits(self):
        self.assertNotIn("font-feature-settings", _css())
        self.assertIn("tabular-nums", self.rule(".table .table__num"))

    def test_viewport_height_has_dynamic_fallback(self):
        for selector, body in _rules(_css()):
            if "100vh" in body:
                self.assertIn("100dvh", body, selector)

    def test_overlays_contain_scroll(self):
        for selector in (".sidebar", ".side-panel"):
            found = [body for sel, body in _rules(_css()) if sel == selector and "overflow" in body]
            self.assertTrue(found and all("overscroll-behavior: contain" in body for body in found), selector)

    def test_rings_are_not_inset_shadows(self):
        self.assertNotIn("box-shadow: inset", _css())

    def test_cell_link_has_a_real_hit_area(self):
        self.assertIn("min-height: 2.5rem", self.rule(".cell__link"))

    def test_nav_soon_tag_is_styled(self):
        self.assertIn("color", self.rule(".nav__soon"))

    def test_cell_secondary_text_is_readable_on_cell_backgrounds(self):
        t = _tokens()
        # фоны, которые реально бывают у ячеек сетки
        for name in ("--st-dayoff-bg", "--st-holiday-bg", "--st-draft-bg", "--st-changed-bg", "--st-error-bg"):
            self.assertGreaterEqual(contrast(t["--ink-2"], t[name]), 4.5, name)
        for selector in (".cell__cab", ".cell__add"):
            self.assertIn("var(--ink-2)", self.rule(selector))


class ThreeLineCellStyleTests(SimpleTestCase):
    def rule(self, selector):
        return AuditFixesTests.rule(self, selector)

    def test_density_modes_exist(self):
        css = _css()
        self.assertIn('[data-density="compact"]', css)
        self.assertIn(".cell__hours", css)

    def test_cell_lines_use_the_scale_and_no_small_text(self):
        for selector in (".cell__hours", ".cell__cab", ".cell__time"):
            body = self.rule(selector)
            self.assertIn("var(--text-sm)", body, selector)
            self.assertNotIn("var(--text-xs)", body, selector)

    def test_hours_use_secondary_ink(self):
        self.assertIn("var(--ink-2)", self.rule(".cell__hours"))

    def test_error_cell_keeps_readable_secondary_lines(self):
        css = _css()
        self.assertIn(".cell--error .cell__hours", css)
        self.assertIn("var(--st-error-ink)", self.rule(".cell--error .cell__cab"))

    def test_compact_mode_hides_the_extra_lines_and_the_flag(self):
        css = _css()
        self.assertRegex(css, r'\[data-density="compact"\][^{]*\.cell__hours[^{]*\{[^}]*display: none')
        self.assertRegex(css, r'\[data-density="compact"\][^{]*\.cell__flag[^{]*\{[^}]*display: none')

    def test_detailed_rows_are_three_lines_high(self):
        self.assertIn("calc(3 * 1.375rem)", _css())
