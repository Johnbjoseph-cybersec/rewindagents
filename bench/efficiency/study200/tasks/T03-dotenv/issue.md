Issue #12: values containing `#` are cut off

`PASSWORD="abc#123"` is read as `"abc` and `URL=http://h/p#frag` as `http://h/p`. The module docstring
describes when `#` starts a comment and how quoted values work; the parser does not follow it.
