import unittest

from semverlite import bump


class HiddenBump(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(bump("1.2.3", "major"), "2.0.0")
        self.assertEqual(bump("1.2.3-rc.1+b", "minor"), "1.3.0")
        self.assertEqual(bump("1.2.3", "patch"), "1.2.4")
        self.assertEqual(bump("1.2.3-rc.1", "patch"), "1.2.3")
        self.assertEqual(bump("1.2.3+build.5", "patch"), "1.2.4")

    def test_prerelease(self):
        self.assertEqual(bump("1.2.3-rc.1", "prerelease"), "1.2.3-rc.2")
        self.assertEqual(bump("1.2.3-rc.9", "prerelease"), "1.2.3-rc.10")
        self.assertEqual(bump("1.2.3-rc", "prerelease"), "1.2.3-rc.1")
        self.assertEqual(bump("1.2.3", "prerelease"), "1.2.4-0")
        self.assertEqual(bump("1.2.3-0+b", "prerelease"), "1.2.3-1")

    def test_errors(self):
        self.assertRaises(ValueError, bump, "1.2.3", "build")
        self.assertRaises(ValueError, bump, "1.2", "patch")
