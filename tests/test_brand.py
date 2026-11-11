"""brand/ checks: palette contrast, BRAND.md in sync with contrast_check.py, scope words."""
import importlib.util
import io
import os
import re
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")

# Same pattern as the scope guard in FIRE's bin/launch_gate.sh. It lives in tests/ because the gate skips tests/.
SCOPE = re.compile(
    r"uneeguard|uneesec|uneeone|firewall|gateway|guardrail|red[ -]?team|jailbreak|prompt[ -]?injection|"
    r"shadow ai|ai inventory|policy (rule|engine|enforce)|block(s|ed|ing)? (the |a |an )?(call|action|command|tool)",
    re.I)


def load_checker():
    spec = importlib.util.spec_from_file_location("contrast_check", os.path.join(BRAND, "contrast_check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def brand_md():
    with open(os.path.join(BRAND, "BRAND.md"), encoding="utf-8") as f:
        return f.read()


class TestBrand(unittest.TestCase):
    def test_every_pair_meets_wcag(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(load_checker().main(), 0)

    def test_known_ratio(self):
        cc = load_checker()
        self.assertAlmostEqual(cc.ratio("#000000", "#FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(cc.ratio("#777777", "#777777"), 1.0, places=6)

    def test_palette_table_matches_checker(self):
        rows = dict(re.findall(r"^\| (\w+) \| (#[0-9A-Fa-f]{6}) \|", brand_md(), re.M))
        self.assertEqual({k: v.upper() for k, v in rows.items()},
                         {k: v.upper() for k, v in load_checker().PALETTE.items()})

    def test_pasted_contrast_table_is_current(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            load_checker().main()
        self.assertIn(buf.getvalue().strip(), brand_md())

    def test_no_scope_words_in_brand(self):
        for dirpath, _, files in os.walk(BRAND):
            for name in files:
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except UnicodeDecodeError:
                    continue
                m = SCOPE.search(text)
                self.assertIsNone(m, "%s: %r" % (path, m and m.group(0)))

    def test_credit_line(self):
        self.assertIn("made by John B Joseph", brand_md())


if __name__ == "__main__":
    unittest.main()
