Issue #88: `**/*.py` does not match top-level files

`match("**/*.py", "a.py")` is False, but it matches `src/a.py`. The docstring says `**` matches zero or more
whole segments, like gitignore. Please make `**` behave as documented.
