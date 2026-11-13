import unittest

from spans import subtract


class HiddenSubtract(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(subtract([(0, 10)], (3, 5)), [(0, 3), (5, 10)])
        self.assertEqual(subtract([(0, 10)], (0, 10)), [])
        self.assertEqual(subtract([(0, 10)], (-5, 3)), [(3, 10)])
        self.assertEqual(subtract([(0, 3), (3, 6)], (6, 9)), [(0, 6)])
        self.assertEqual(subtract([(0, 2), (4, 6)], (1, 5)), [(0, 1), (5, 6)])
        self.assertEqual(subtract([(0, 10)], (4, 4)), [(0, 10)])
        self.assertEqual(subtract([], (0, 1)), [])

    def test_invalid_and_unmodified(self):
        self.assertRaises(ValueError, subtract, [(0, 1)], (3, 2))
        self.assertRaises(ValueError, subtract, [(2, 1)], (0, 1))
        data = [[0, 4]]
        subtract(data, (1, 2))
        self.assertEqual(data, [[0, 4]])
