import unittest

from ttlcache import TTLCache


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class HiddenFix(unittest.TestCase):
    def setUp(self):
        self.k = Clock()

    def test_boundary(self):
        c = TTLCache(3, 10, self.k)
        c.set("a", 1)
        self.k.t = 9.999
        self.assertEqual(c.get("a"), 1)
        self.k.t = 10
        self.assertIsNone(c.get("a"))
        self.assertEqual(len(c), 0)

    def test_get_does_not_extend(self):
        c = TTLCache(3, 10, self.k)
        c.set("a", 1)
        self.k.t = 8
        c.get("a")
        self.k.t = 11
        self.assertNotIn("a", c)

    def test_set_existing_refreshes(self):
        c = TTLCache(3, 10, self.k)
        c.set("a", 1)
        self.k.t = 8
        c.set("a", 2)
        self.k.t = 15
        self.assertEqual(c.get("a"), 2)
        self.assertEqual(len(c), 1)

    def test_expired_evicted_before_lru(self):
        c = TTLCache(2, 10, self.k)
        c.set("old", 0)
        self.k.t = 5
        c.set("b", 1)
        self.k.t = 6
        c.get("old")
        self.k.t = 12
        c.set("c", 2)
        self.assertIn("b", c)
        self.assertIn("c", c)
        self.assertEqual(len(c), 2)

    def test_set_existing_does_not_evict(self):
        c = TTLCache(2, 10, self.k)
        c.set("a", 1)
        c.set("b", 2)
        c.set("a", 3)
        self.assertIn("b", c)
        self.assertEqual(c.get("a"), 3)

    def test_lru_order_and_contains_no_recency(self):
        c = TTLCache(2, 100, self.k)
        c.set("a", 1)
        c.set("b", 2)
        self.assertIn("a", c)
        c.set("c", 3)
        self.assertNotIn("a", c)
        self.assertIn("b", c)

    def test_len_and_in_live_only(self):
        c = TTLCache(5, 10, self.k)
        c.set("a", 1)
        self.k.t = 5
        c.set("b", 2)
        self.k.t = 10
        self.assertEqual(len(c), 1)
        self.assertNotIn("a", c)
        self.assertIn("b", c)

    def test_get_default(self):
        c = TTLCache(1, 1, self.k)
        self.assertEqual(c.get("x", 7), 7)
        c.set("x", None)
        self.assertIsNone(c.get("x", 7))

    def test_validation(self):
        for cap, ttl in ((0, 1), (1, 0), (1, -1), (-1, 5)):
            self.assertRaises(ValueError, TTLCache, cap, ttl, self.k)
