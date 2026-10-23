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
