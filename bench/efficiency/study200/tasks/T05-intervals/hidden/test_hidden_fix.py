import unittest

from spans import merge, total_length


class HiddenFix(unittest.TestCase):
    def test_touching_chain(self):
        self.assertEqual(merge([(5, 7), (1, 3), (3, 5)]), [(1, 7)])

    def test_empty_dropped(self):
        self.assertEqual(merge([(2, 2)]), [])
        self.assertEqual(merge([(1, 3), (3, 3), (4, 4)]), [(1, 3)])
        self.assertEqual(merge([(3, 3), (1, 3)]), [(1, 3)])
        self.assertEqual(merge([(1, 2), (2, 2), (3, 4)]), [(1, 2), (3, 4)])

    def test_contained_and_dupes(self):
        self.assertEqual(merge([(1, 10), (2, 3), (1, 10)]), [(1, 10)])

    def test_input_forms_not_modified(self):
        data = [[4, 6], [1, 2]]
        self.assertEqual(merge(data), [(1, 2), (4, 6)])
        self.assertEqual(data, [[4, 6], [1, 2]])
        t = ((3, 4), (1, 3))
        self.assertEqual(merge(t), [(1, 4)])
        self.assertEqual(merge(iter([(0, 1)])), [(0, 1)])
        self.assertEqual(merge([]), [])

    def test_tuples_out(self):
        self.assertIsInstance(merge([[1, 2]])[0], tuple)

    def test_invalid(self):
        self.assertRaises(ValueError, merge, [(1, 2), (5, 4)])
        self.assertRaises(ValueError, total_length, [(5, 4)])

    def test_negative_and_length(self):
        self.assertEqual(merge([(-5, -2), (-2, 0)]), [(-5, 0)])
        self.assertEqual(total_length([(0, 2), (1, 3), (10, 10)]), 3)
