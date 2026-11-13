import random
import unittest

from money import allocate


class HiddenFix(unittest.TestCase):
    def test_sum_always_total(self):
        rng = random.Random(7)
        for _ in range(300):
            ws = [rng.randint(0, 9) for _ in range(rng.randint(1, 6))]
            if not any(ws):
                ws[0] = 1
            t = rng.randint(-10 ** 6, 10 ** 6)
            got = allocate(t, ws)
            self.assertEqual(sum(got), t, (t, ws))
            self.assertEqual(len(got), len(ws))

    def test_largest_remainder(self):
        self.assertEqual(allocate(10, [3, 3, 4]), [3, 3, 4])
        self.assertEqual(allocate(100, [2, 1, 1]), [50, 25, 25])
        self.assertEqual(allocate(5, [1, 1, 1, 1]), [2, 1, 1, 1])
        self.assertEqual(allocate(7, [1, 2]), [2, 5])
        self.assertEqual(allocate(10, [1, 1, 1, 7]), [1, 1, 1, 7])
        self.assertEqual(allocate(2, [1, 1, 1]), [1, 1, 0])
        self.assertEqual(allocate(11, [5, 5, 1]), [5, 5, 1])
        self.assertEqual(allocate(1, [3, 5, 2]), [0, 1, 0])

    def test_big_numbers_exact(self):
        self.assertEqual(allocate(10 ** 18 + 1, [1, 1]), [5 * 10 ** 17 + 1, 5 * 10 ** 17])

    def test_zero_and_negative(self):
        self.assertEqual(allocate(100, [0, 1, 1]), [0, 50, 50])
        self.assertEqual(allocate(1, [0, 1]), [0, 1])
        self.assertEqual(allocate(-100, [1, 1, 1]), [-34, -33, -33])
        self.assertEqual(allocate(0, [1, 2]), [0, 0])

    def test_validation(self):
        for bad in ([], [0, 0], [1, -1], [1.5, 1]):
            self.assertRaises(ValueError, allocate, 10, bad)

    def test_input_not_modified(self):
        ws = [3, 1]
        allocate(10, ws)
        self.assertEqual(ws, [3, 1])
