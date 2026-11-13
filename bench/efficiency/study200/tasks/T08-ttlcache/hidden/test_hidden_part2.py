import unittest

from ttlcache import TTLCache


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class HiddenGetOrSet(unittest.TestCase):
    def test_get_or_set(self):
        k = Clock()
        c = TTLCache(2, 10, k)
        calls = []

        def make():
            calls.append(1)
            return len(calls)

        self.assertEqual(c.get_or_set("a", make), 1)
        self.assertEqual(c.get_or_set("a", make), 1)
        k.t = 10
        self.assertEqual(c.get_or_set("a", make), 2)
        self.assertEqual(len(calls), 2)

    def test_none_and_raise(self):
        c = TTLCache(2, 10, Clock())
        n = []
        c.get_or_set("n", lambda: n.append(1))
        c.get_or_set("n", lambda: n.append(1))
        self.assertEqual(len(n), 1)

        def boom():
            raise KeyError("x")

        self.assertRaises(KeyError, c.get_or_set, "z", boom)
        self.assertNotIn("z", c)

    def test_recency(self):
        c = TTLCache(2, 10, Clock())
        c.set("a", 1)
        c.set("b", 2)
        c.get_or_set("a", lambda: 9)
        c.set("c", 3)
        self.assertIn("a", c)
        self.assertNotIn("b", c)
