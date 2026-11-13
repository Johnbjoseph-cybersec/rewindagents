import unittest

from money import allocate


class MoneyTest(unittest.TestCase):
    def test_even(self):
        self.assertEqual(allocate(100, [1, 1]), [50, 50])

    def test_proportional(self):
        self.assertEqual(allocate(1000, [1, 3]), [250, 750])

    def test_issue_cent_lost(self):
        # issue #7: a cent goes missing
        self.assertEqual(allocate(100, [1, 1, 1]), [34, 33, 33])


if __name__ == "__main__":
    unittest.main()
