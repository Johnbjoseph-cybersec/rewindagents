import unittest

from coupons import apply_coupon


class HiddenCoupons(unittest.TestCase):
    def test_save10(self):
        self.assertEqual(apply_coupon(1000, "SAVE10"), 900)
        self.assertEqual(apply_coupon(995, "save10"), 896)     # 895.5 -> 896

    def test_flat500(self):
        self.assertEqual(apply_coupon(1200, " FLAT500 "), 700)
        self.assertEqual(apply_coupon(300, "flat500"), 0)

    def test_unknown(self):
        with self.assertRaises(ValueError):
            apply_coupon(100, "FREE")
