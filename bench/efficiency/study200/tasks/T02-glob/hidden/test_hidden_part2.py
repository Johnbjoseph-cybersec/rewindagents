import unittest

from globmatch import filter_paths


class HiddenFilter(unittest.TestCase):
    def test_last_match_wins(self):
        paths = ["a.py", "b.txt", "src/c.py", "src/gen/d.py"]
        self.assertEqual(filter_paths(["**/*.py", "!src/gen/**"], paths), ["a.py", "src/c.py"])
        self.assertEqual(filter_paths(["!src/gen/**", "**/*.py"], paths), ["a.py", "src/c.py", "src/gen/d.py"])

    def test_ignored_and_literal_bang(self):
        self.assertEqual(filter_paths(["", "# *.py", "*.txt"], ["a.py", "b.txt"]), ["b.txt"])
        self.assertEqual(filter_paths(["\\!x"], ["!x", "x"]), ["!x"])

    def test_order_kept(self):
        self.assertEqual(filter_paths(["*"], ["z", "a"]), ["z", "a"])
        self.assertEqual(filter_paths([], ["a"]), [])
