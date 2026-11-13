import unittest

from qs import build_query, parse_query


class HiddenBuild(unittest.TestCase):
    def test_build(self):
        self.assertEqual(build_query({"a": "1", "b": "x y"}), "a=1&b=x+y")
        self.assertEqual(build_query({"q": "rock&roll", "t": ["1", "2"]}), "q=rock%26roll&t=1&t=2")
        self.assertEqual(build_query({"n": "é~-._"}), "n=%C3%A9~-._")
        self.assertEqual(build_query({"a b": "1+1"}), "a+b=1%2B1")
        self.assertEqual(build_query({"e": [], "f": ""}), "f=")
        self.assertEqual(build_query({}), "")

    def test_round_trip(self):
        d = {"q": "a=b&c", "u": "€ 😀/?", "t": ["x", "", "%"]}
        self.assertEqual(parse_query(build_query(d)), d)

    def test_types(self):
        self.assertRaises(TypeError, build_query, {"a": 1})
        self.assertRaises(TypeError, build_query, {"a": ["1", 2]})
