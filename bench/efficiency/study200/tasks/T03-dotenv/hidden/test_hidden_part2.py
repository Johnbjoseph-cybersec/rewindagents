import unittest

from envfile import dumps, parse


class HiddenDumps(unittest.TestCase):
    def test_format(self):
        self.assertEqual(dumps({"A": "1", "B": "x y"}), 'A=1\nB="x y"\n')
        self.assertEqual(dumps({"U": "http://h:80/p,q@r_s-t.u"}), "U=http://h:80/p,q@r_s-t.u\n")
        self.assertEqual(dumps({"E": ""}), 'E=""\n')
        self.assertEqual(dumps({"Q": 'a"b\\c\nd'}), 'Q="a\\"b\\\\c\\nd"\n')

    def test_round_trip(self):
        m = {"A": "a #b", "B": "#x", "C": "it's", "D": " lead", "E": "l1\nl2", "F": "\\n", "G": "x#y"}
        self.assertEqual(parse(dumps(m)), m)

    def test_bad_name(self):
        self.assertRaises(ValueError, dumps, {"1A": "x"})
