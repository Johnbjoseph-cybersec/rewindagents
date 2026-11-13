import unittest

from qs import parse_query as p


class HiddenFix(unittest.TestCase):
    def test_decode_after_split(self):
        self.assertEqual(p("q=rock%26roll"), {"q": "rock&roll"})
        self.assertEqual(p("a%3Db=c%3Dd"), {"a=b": "c=d"})
        self.assertEqual(p("x=1=2"), {"x": "1=2"})

    def test_plus(self):
        self.assertEqual(p("a=1%2B1"), {"a": "1+1"})
        self.assertEqual(p("a+b=c+d"), {"a b": "c d"})

    def test_utf8(self):
        self.assertEqual(p("n=%C3%A9t%C3%A9"), {"n": "été"})
        self.assertEqual(p("e=%E2%82%AC%F0%9F%98%80"), {"e": "€😀"})
        self.assertEqual(p("n=%c3%a9"), {"n": "é"})
        self.assertRaises(ValueError, p, "n=%C3")
        self.assertRaises(ValueError, p, "n=%FF")

    def test_bad_percent_kept(self):
        self.assertEqual(p("a=100%"), {"a": "100%"})
        self.assertEqual(p("a=%zz1"), {"a": "%zz1"})
        self.assertEqual(p("a=%4"), {"a": "%4"})
        self.assertEqual(p("a=50%25"), {"a": "50%"})

    def test_blank_and_flags(self):
        self.assertEqual(p("flag&a="), {"flag": "", "a": ""})
        self.assertEqual(p("a=1&&b=2&"), {"a": "1", "b": "2"})
        self.assertEqual(p(""), {})
        self.assertEqual(p("?"), {})
        self.assertEqual(p("a=1;b=2"), {"a": "1;b=2"})

    def test_repeats(self):
        self.assertEqual(p("t=1&u=0&t=2&t=3"), {"t": ["1", "2", "3"], "u": "0"})
        self.assertEqual(p("t=&t="), {"t": ["", ""]})
