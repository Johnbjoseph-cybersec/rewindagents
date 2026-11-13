import unittest

from globmatch import match


class HiddenFix(unittest.TestCase):
    def test_leading(self):
        self.assertTrue(match("**/x", "x"))
        self.assertTrue(match("**/x", "a/b/x"))
        self.assertFalse(match("**/x", "ax"))
        self.assertFalse(match("**/x", "a/bx"))

    def test_trailing(self):
        self.assertTrue(match("a/**", "a/b"))
        self.assertTrue(match("a/**", "a/b/c"))
        self.assertFalse(match("a/**", "a"))
        self.assertFalse(match("a/**", "ab/c"))

    def test_middle(self):
        self.assertTrue(match("a/**/b", "a/b"))
        self.assertTrue(match("a/**/b", "a/x/y/b"))
        self.assertFalse(match("a/**/b", "a/xb"))
        self.assertFalse(match("a/**/b", "ab"))

    def test_not_a_segment_is_star(self):
        self.assertTrue(match("a**b", "axxb"))
        self.assertFalse(match("a**b", "a/b"))
        self.assertFalse(match("x/a**", "x/a/b"))

    def test_only(self):
        self.assertTrue(match("**", "a"))
        self.assertTrue(match("**", "a/b/c"))

    def test_star_never_crosses(self):
        self.assertFalse(match("*.py", "a/b.py"))
        self.assertFalse(match("a/*/c", "a/b/x/c"))
        self.assertFalse(match("?", "/"))

    def test_classes_and_literals(self):
        self.assertTrue(match("[!a]x", "bx"))
        self.assertFalse(match("[!a]x", "ax"))
        self.assertFalse(match("a.c", "abc"))
        self.assertTrue(match("a+b(1)", "a+b(1)"))
        self.assertFalse(match("*.PY", "a.py"))
