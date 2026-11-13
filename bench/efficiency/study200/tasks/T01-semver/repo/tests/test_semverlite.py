import unittest

from semverlite import compare, parse, sort_versions


class SemverTest(unittest.TestCase):
    def test_parse(self):
        v = parse("1.2.3-beta.1+exp.sha")
        self.assertEqual((v.major, v.minor, v.patch, v.prerelease, v.build), (1, 2, 3, "beta.1", "exp.sha"))
        self.assertRaises(ValueError, parse, "1.2")

    def test_numeric_core(self):
        self.assertEqual(compare("1.10.0", "1.9.0"), 1)
        self.assertEqual(compare("2.0.0", "2.0.0"), 0)

    def test_issue_prerelease_is_lower(self):
        # issue #41
        self.assertEqual(compare("1.0.0-alpha", "1.0.0"), -1)
        self.assertEqual(sort_versions(["1.0.0-rc.10", "1.0.0", "1.0.0-rc.2"]),
                         ["1.0.0-rc.2", "1.0.0-rc.10", "1.0.0"])


if __name__ == "__main__":
    unittest.main()
