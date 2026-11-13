import unittest

from durations import parse_duration as p


class HiddenFix(unittest.TestCase):
    def test_compounds(self):
        self.assertEqual(p("1h30m"), 5400.0)
        self.assertEqual(p("1h 30m"), 5400.0)
        self.assertEqual(p("  2d1s "), 172801.0)
        self.assertAlmostEqual(p("1m500ms"), 60.5)
        self.assertAlmostEqual(p("1s 1ms"), 1.001)
        self.assertEqual(p("0s"), 0.0)

    def test_m_vs_ms(self):
        self.assertAlmostEqual(p("5ms"), 0.005)
        self.assertEqual(p("5m"), 300.0)
        self.assertRaises(ValueError, p, "5ms5m")

    def test_negative(self):
        self.assertEqual(p("-1h30m"), -5400.0)
        self.assertRaises(ValueError, p, "-")
        self.assertRaises(ValueError, p, "1h-30m")

    def test_errors(self):
        for bad in ("", "   ", "h", "1", "1h30", "30m1h", "1h1h", "1H", "1h,30m", "1hour",
                    "1h 30", "1h  x"):
            self.assertRaises(ValueError, p, bad)

    def test_type(self):
        self.assertIsInstance(p("2s"), float)
