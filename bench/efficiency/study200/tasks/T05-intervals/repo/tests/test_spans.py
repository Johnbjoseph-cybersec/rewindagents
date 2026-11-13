import unittest

from spans import merge, total_length


class SpansTest(unittest.TestCase):
    def test_overlap(self):
        self.assertEqual(merge([(5, 8), (1, 4), (3, 6)]), [(1, 8)])

    def test_disjoint(self):
        self.assertEqual(merge([(1, 2), (4, 5)]), [(1, 2), (4, 5)])

    def test_issue_touching(self):
        # issue #19: touching intervals are not merged
        self.assertEqual(merge([(1, 3), (3, 5)]), [(1, 5)])
        self.assertEqual(total_length([(1, 3), (3, 5)]), 4)


if __name__ == "__main__":
    unittest.main()
