import unittest

from qs import parse_query


class QueryTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_query("a=1&b=x+y"), {"a": "1", "b": "x y"})

    def test_repeated(self):
        self.assertEqual(parse_query("?t=1&t=2"), {"t": ["1", "2"]})

    def test_issue_encoded_ampersand(self):
        # issue #77: an encoded "&" in a value splits the pair
        self.assertEqual(parse_query("q=rock%26roll&n=1"), {"q": "rock&roll", "n": "1"})


if __name__ == "__main__":
    unittest.main()
