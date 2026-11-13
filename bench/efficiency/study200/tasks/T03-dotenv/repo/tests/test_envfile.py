import unittest

from envfile import parse


class EnvTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse("A=1\n\n# c\nexport B = two\n"), {"A": "1", "B": "two"})

    def test_quotes(self):
        self.assertEqual(parse("A='x y'\nB=\"z\""), {"A": "x y", "B": "z"})

    def test_bad_name(self):
        self.assertRaises(ValueError, parse, "1A=x")

    def test_issue_hash_in_quotes(self):
        # issue #12: a quoted value containing # is cut off
        self.assertEqual(parse('PASSWORD="abc#123"'), {"PASSWORD": "abc#123"})
        self.assertEqual(parse("URL=http://h/p#frag"), {"URL": "http://h/p#frag"})


if __name__ == "__main__":
    unittest.main()
