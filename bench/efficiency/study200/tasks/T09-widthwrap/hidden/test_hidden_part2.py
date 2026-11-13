import unittest

from termtext import pad


class HiddenPad(unittest.TestCase):
    def test_pad(self):
        self.assertEqual(pad("ab", 4), "ab  ")
        self.assertEqual(pad("日", 4), "日  ")
        self.assertEqual(pad("日", 4, "right"), "  日")
        self.assertEqual(pad("ab", 5, "center"), " ab  ")
        self.assertEqual(pad("é", 3, "right"), "  é")
        self.assertEqual(pad("日本語", 4), "日本語")
        self.assertRaises(ValueError, pad, "a", 3, "middle")
