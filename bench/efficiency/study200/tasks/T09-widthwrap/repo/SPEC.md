# termtext: pad (planned)

`pad(text, width, align="left")` returns `text` padded with spaces to display width `width` (measured with
`text_width`). `align` is `"left"` (spaces after), `"right"` (spaces before) or `"center"` (the extra space,
when the padding is odd, goes on the right). Text already as wide or wider than `width` is returned unchanged.
Any other `align` raises ValueError.
