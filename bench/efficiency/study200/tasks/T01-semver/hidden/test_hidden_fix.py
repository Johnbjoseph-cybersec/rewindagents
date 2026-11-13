import unittest

from semverlite import compare, parse, sort_versions


class HiddenFix(unittest.TestCase):
    def test_spec_chain(self):
        chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
                 "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        for i in range(len(chain) - 1):
            self.assertEqual(compare(chain[i], chain[i + 1]), -1, (chain[i], chain[i + 1]))
            self.assertEqual(compare(chain[i + 1], chain[i]), 1, (chain[i + 1], chain[i]))
        self.assertEqual(sort_versions(list(reversed(chain))), chain)

    def test_numeric_lower_than_alnum(self):
        self.assertEqual(compare("1.0.0-1", "1.0.0-a"), -1)
        self.assertEqual(compare("1.0.0-99", "1.0.0-1a"), -1)

    def test_lexical_ascii(self):
        self.assertEqual(compare("1.0.0-B", "1.0.0-a"), -1)
        self.assertEqual(compare("1.0.0-alpha-2", "1.0.0-alpha-10"), 1)

    def test_build_ignored(self):
        self.assertEqual(compare("1.0.0+a", "1.0.0+b"), 0)
        self.assertEqual(compare("1.0.0-rc.1+x", "1.0.0-rc.1"), 0)
        self.assertEqual(sort_versions(["1.0.0+b", "1.0.0+a"]), ["1.0.0+b", "1.0.0+a"])

    def test_core_still_numeric(self):
        self.assertEqual(compare("1.0.10", "1.0.9"), 1)
        self.assertEqual(compare("0.9.0-rc.1", "0.10.0-alpha"), -1)
        self.assertEqual(compare("2.0.0-alpha", "1.99.99"), 1)

    def test_parse_unchanged(self):
        self.assertEqual(str(parse(" 1.2.3-x.7+b ")), "1.2.3-x.7+b")
        for bad in ("1.2.3-", "v1.2.3", "1.2.3+"):
            self.assertRaises(ValueError, parse, bad)
