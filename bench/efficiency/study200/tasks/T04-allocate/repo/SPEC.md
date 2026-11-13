# money: format_cents (planned)

`format_cents(cents, symbol="$")` formats an integer amount of cents:

- thousands separated by `,`, always two decimals: `123456` -> `"$1,234.56"`, `5` -> `"$0.05"`
- negative amounts put the sign before the symbol: `-123456` -> `"-$1,234.56"`; zero is `"$0.00"`
- `symbol` may be any string, including empty: `format_cents(100, "")` -> `"1.00"`
- anything that is not an int (a float, a bool, a str) raises TypeError
