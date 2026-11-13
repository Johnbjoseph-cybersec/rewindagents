import unittest

from deps import toposort


class DepsTest(unittest.TestCase):
    def test_chain(self):
        self.assertEqual(toposort({"c": ["b"], "b": ["a"], "a": []}), ["a", "b", "c"])

    def test_issue_cycle(self):
        # issue #23: a cycle is silently accepted
        from deps import CycleError
        self.assertRaises(CycleError, toposort, {"a": ["b"], "b": ["a"]})


if __name__ == "__main__":
    unittest.main()
