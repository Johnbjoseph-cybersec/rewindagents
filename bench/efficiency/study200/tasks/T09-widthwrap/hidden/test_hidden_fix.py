import unittest

from termtext import char_width, text_width, wrap


class HiddenFix(unittest.TestCase):
    def test_widths(self):
        self.assertEqual(char_width("a"), 1)
        self.assertEqual(char_width("語"), 2)
        self.assertEqual(char_width("Ａ"), 2)  # fullwidth A, "F"
        self.assertEqual(char_width("́"), 0)
        self.assertEqual(char_width("‍"), 0)
        self.assertEqual(text_width("é"), 1)
        self.assertEqual(text_width(""), 0)

    def test_greedy_mixed(self):
        self.assertEqual(wrap("ab 日本 c", 6), ["ab", "日本 c"])
        self.assertEqual(wrap("a  b   c", 3), ["a b", "c"])

    def test_long_word_broken(self):
        self.assertEqual(wrap("abcdefg", 3), ["abc", "def", "g"])
        self.assertEqual(wrap("日本語", 3), ["日", "本", "語"])
        self.assertEqual(wrap("a日本", 4), ["a日", "本"])

    def test_combining_stays(self):
        self.assertEqual(wrap("ééé", 2), ["éé", "é"])

    def test_wider_than_width(self):
        self.assertEqual(wrap("日x", 1), ["日", "x"])

    def test_never_wider(self):
        for text in ("日本語のテキスト と English words mixed", "ｆｕｌｌｗｉｄｔｈ ｔｅｘｔ ok", "a" * 23):
            for w in range(2, 12):
                for line in wrap(text, w):
                    self.assertLessEqual(text_width(line), w, (text, w, line))

    def test_empty_and_bad(self):
        self.assertEqual(wrap("", 5), [])
        self.assertEqual(wrap("   ", 5), [])
        self.assertRaises(ValueError, wrap, "a", 0)
