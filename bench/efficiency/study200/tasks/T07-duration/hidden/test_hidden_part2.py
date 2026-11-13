import unittest

from durations import format_duration as f, parse_duration


class HiddenFormat(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(f(5400), "1h30m")
        self.assertEqual(f(90061), "1d1h1m1s")
        self.assertEqual(f(0.25), "250ms")
        self.assertEqual(f(61.5), "1m1s500ms")
        self.assertEqual(f(0), "0s")
        self.assertEqual(f(-90), "-1m30s")
        self.assertEqual(f(1.0004), "1s")
        self.assertEqual(f(1.0006), "1s1ms")
        self.assertEqual(f(86400), "1d")

    def test_round_trip(self):
        for x in (0.001, 59.999, 3600.5, 123456.789, -0.5):
            self.assertAlmostEqual(parse_duration(f(x)), round(x, 3))
