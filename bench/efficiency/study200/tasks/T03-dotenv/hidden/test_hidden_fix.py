import unittest

from envfile import parse


class HiddenFix(unittest.TestCase):
    def test_hash_rules(self):
        self.assertEqual(parse("A=x #c"), {"A": "x"})
        self.assertEqual(parse("A=x#c"), {"A": "x#c"})
        self.assertEqual(parse("A=x\t#c"), {"A": "x"})
        self.assertEqual(parse("A='a #b' # note"), {"A": "a #b"})
        self.assertEqual(parse('A="a #b"   # note'), {"A": "a #b"})
        self.assertEqual(parse("A= #only comment"), {"A": ""})

    def test_double_quote_escapes(self):
        self.assertEqual(parse(r'A="l1\nl2"'), {"A": "l1\nl2"})
        self.assertEqual(parse(r'A="say \"hi\""'), {"A": 'say "hi"'})
        self.assertEqual(parse(r'A="back\\slash"'), {"A": "back\\slash"})
        self.assertEqual(parse(r'A="keep\t"'), {"A": "keep\\t"})

    def test_single_quotes_literal(self):
        self.assertEqual(parse(r"A='l1\nl2'"), {"A": "l1\\nl2"})
        self.assertEqual(parse("A='it\"s'"), {"A": 'it"s'})

    def test_after_quote(self):
        with self.assertRaises(ValueError) as cm:
            parse('X=1\nA="a" b')
        self.assertIn("2", str(cm.exception))
        self.assertEqual(parse('A="a"   '), {"A": "a"})

    def test_misc(self):
        self.assertEqual(parse("export\tA=1\n  # x\nA=2"), {"A": "2"})
        self.assertEqual(parse("exported=1"), {"exported": "1"})
        self.assertEqual(parse("A = b c  "), {"A": "b c"})
        self.assertEqual(parse("A="), {"A": ""})
        self.assertEqual(parse('A=""'), {"A": ""})
        with self.assertRaises(ValueError) as cm:
            parse("\n\nB-C=1")
        self.assertIn("3", str(cm.exception))
