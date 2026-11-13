import unittest

from globmatch import match


class GlobTest(unittest.TestCase):
    def test_star(self):
        self.assertTrue(match("*.py", "setup.py"))
        self.assertFalse(match("*.py", "pkg/setup.py"))

    def test_question_and_class(self):
        self.assertTrue(match("file?.txt", "file1.txt"))
        self.assertTrue(match("[a-c]x", "bx"))

    def test_issue_double_star_prefix(self):
        # issue #88: "**/*.py" must also match files at the top level
        self.assertTrue(match("**/*.py", "a.py"))
        self.assertTrue(match("**/*.py", "src/pkg/a.py"))


if __name__ == "__main__":
    unittest.main()
