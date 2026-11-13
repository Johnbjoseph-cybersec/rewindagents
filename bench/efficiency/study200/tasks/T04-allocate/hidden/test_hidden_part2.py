import unittest

from money import format_cents


class HiddenFormat(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_cents(123456), "$1,234.56")
        self.assertEqual(format_cents(5), "$0.05")
        self.assertEqual(format_cents(0), "$0.00")
        self.assertEqual(format_cents(-123456), "-$1,234.56")
        self.assertEqual(format_cents(-5), "-$0.05")
        self.assertEqual(format_cents(100000000), "$1,000,000.00")
        self.assertEqual(format_cents(100, ""), "1.00")
        self.assertEqual(format_cents(250, "EUR "), "EUR 2.50")

    def test_types(self):
        for bad in (1.0, True, "100"):
            self.assertRaises(TypeError, format_cents, bad)
