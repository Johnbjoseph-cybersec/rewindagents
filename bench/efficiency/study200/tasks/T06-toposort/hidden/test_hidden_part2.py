import unittest

from deps import CycleError, levels


class HiddenLevels(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(levels({"app": ["lib", "cfg"], "lib": ["cfg"]}), [["cfg"], ["lib"], ["app"]])
        self.assertEqual(levels({"b": [], "a": [], "c": ["a"]}), [["a", "b"], ["c"]])
        self.assertEqual(levels({"t": ["x", "y"], "y": ["x"], "z": ["x"]}), [["x"], ["y", "z"], ["t"]])
        self.assertEqual(levels({}), [])

    def test_cycle(self):
        self.assertRaises(CycleError, levels, {"a": ["a"]})
