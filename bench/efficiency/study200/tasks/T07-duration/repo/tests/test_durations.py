import unittest

from durations import parse_duration


class DurationTest(unittest.TestCase):
    def test_single(self):
        self.assertEqual(parse_duration("90s"), 90.0)
        self.assertEqual(parse_duration("1.5h"), 5400.0)

    def test_bad_unit(self):
        self.assertRaises(ValueError, parse_duration, "5y")

    def test_issue_compound(self):
        # issue #31: only the first part is read
        self.assertEqual(parse_duration("1h30m"), 5400.0)
        self.assertRaises(ValueError, parse_duration, "1h30")


if __name__ == "__main__":
    unittest.main()
