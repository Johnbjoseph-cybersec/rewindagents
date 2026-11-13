import unittest

from cart import apply_discount, line_total, subtotal


class HiddenCart(unittest.TestCase):
    def test_subtotal_counts_every_line(self):
        self.assertEqual(subtotal([(250, 2), (100, 1), (5, 3)]), 615)
        self.assertEqual(subtotal([(999, 1)]), 999)
        self.assertEqual(subtotal([]), 0)

    def test_negative_qty(self):
        with self.assertRaises(ValueError):
            line_total(100, -1)
        self.assertEqual(line_total(100, 0), 0)

    def test_discount_rounds_half_up(self):
        self.assertEqual(apply_discount(999, 15), 849)     # 849.15
        self.assertEqual(apply_discount(3, 50), 2)         # 1.5 -> 2
        self.assertEqual(apply_discount(1000, 0), 1000)
        self.assertEqual(apply_discount(1000, 100), 0)
        self.assertIsInstance(apply_discount(999, 15), int)

    def test_discount_range(self):
        for bad in (-1, 101):
            with self.assertRaises(ValueError):
                apply_discount(100, bad)
