Issue #64: wide characters overflow the terminal

Lines with Chinese or Japanese text come out twice as wide as `width`: `text_width("日本")` is 2, but on
screen it takes 4 columns, and `wrap()` measures with `len()`. The module docstring defines the display width
and `wrap()`'s docstring how lines must be broken; please implement them.
