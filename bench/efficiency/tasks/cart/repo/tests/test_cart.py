import unittest

from cart import apply_discount, subtotal


class CartTest(unittest.TestCase):
    def test_subtotal(self):
        self.assertEqual(subtotal([(250, 2), (100, 1)]), 600)

    def test_discount(self):
        self.assertEqual(apply_discount(1000, 10), 900)


if __name__ == "__main__":
    unittest.main()
