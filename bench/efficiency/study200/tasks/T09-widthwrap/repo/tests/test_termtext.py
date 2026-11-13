import unittest

from termtext import text_width, wrap


class WrapTest(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(wrap("the quick brown fox", 10), ["the quick", "brown fox"])

    def test_issue_cjk_width(self):
        # issue #64: CJK text overflows the terminal
        self.assertEqual(text_width("日本"), 4)
        self.assertEqual(wrap("日本 語", 4), ["日本", "語"])


if __name__ == "__main__":
    unittest.main()
