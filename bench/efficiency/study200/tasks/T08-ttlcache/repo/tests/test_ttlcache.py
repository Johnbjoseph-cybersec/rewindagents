import unittest

from ttlcache import TTLCache


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class CacheTest(unittest.TestCase):
    def test_set_get(self):
        c = TTLCache(2, 10, Clock())
        c.set("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("b"))

    def test_lru(self):
        c = TTLCache(2, 10, Clock())
        c.set("a", 1)
        c.set("b", 2)
        c.get("a")
        c.set("c", 3)
        self.assertIn("a", c)
        self.assertNotIn("b", c)

    def test_issue_expired_returned(self):
        # issue #52: stale values are served after their ttl
        clock = Clock()
        c = TTLCache(2, 10, clock)
        c.set("a", 1)
        clock.t = 10
        self.assertEqual(c.get("a", "gone"), "gone")


if __name__ == "__main__":
    unittest.main()
