import unittest

from deps import CycleError, toposort


def check_cycle(test, deps, cyc):
    test.assertGreaterEqual(len(cyc), 2)
    test.assertEqual(cyc[0], cyc[-1])
    test.assertEqual(len(set(cyc[:-1])), len(cyc) - 1)
    for a, b in zip(cyc, cyc[1:]):
        test.assertIn(b, deps.get(a, []), (a, b, cyc))


class HiddenFix(unittest.TestCase):
    def test_alphabetical_tiebreak(self):
        self.assertEqual(toposort({"b": [], "a": [], "c": []}), ["a", "b", "c"])
        self.assertEqual(toposort({"z": ["m"], "a": ["m"], "m": []}), ["m", "a", "z"])
        self.assertEqual(toposort({"d": ["a"], "b": [], "a": []}), ["a", "b", "d"])
        self.assertEqual(toposort({"c": [], "b": ["c"], "a": ["b"]}), ["c", "b", "a"])

    def test_insertion_order_irrelevant(self):
        d1 = {"app": ["lib", "cfg"], "lib": ["cfg"], "test": ["app"], "docs": []}
        d2 = dict(reversed(list(d1.items())))
        self.assertEqual(toposort(d1), ["cfg", "docs", "lib", "app", "test"])
        self.assertEqual(toposort(d2), toposort(d1))

    def test_implicit_and_dupes(self):
        self.assertEqual(toposort({"x": ["y", "y"]}), ["y", "x"])
        self.assertEqual(toposort({}), [])

    def test_cycles(self):
        for deps in ({"a": ["b"], "b": ["a"]}, {"a": ["a"]}, {"a": ["b"], "b": ["c"], "c": ["a"], "d": []},
                     {"x": ["a"], "a": ["b"], "b": ["a"]}):
            with self.assertRaises(CycleError) as cm:
                toposort(deps)
            check_cycle(self, deps, cm.exception.cycle)
        self.assertTrue(issubclass(CycleError, ValueError))

    def test_not_modified(self):
        d = {"a": ["b"], "b": []}
        toposort(d)
        self.assertEqual(d, {"a": ["b"], "b": []})
