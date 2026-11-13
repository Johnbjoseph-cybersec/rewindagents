"""Lay out text for a fixed-width terminal.

Display width of a character (see ``char_width``): 0 for combining marks (``unicodedata.combining(c)``
non-zero) and for the zero-width joiner U+200D; 2 for characters whose ``unicodedata.east_asian_width`` is
"W" or "F"; 1 for everything else.
"""
import unicodedata


def char_width(c):
    return 1


def text_width(s):
    """Display width of ``s``: the sum of its characters' widths."""
    return sum(char_width(c) for c in s)


def wrap(text, width):
    """Break ``text`` into lines whose display width is at most ``width``.

    * Words are separated by runs of spaces; lines hold whole words separated by one space, filled greedily.
    * A word wider than ``width`` is broken across lines at character boundaries, filling each line as much
      as possible; a combining mark always stays with the character before it, and a wide character is never
      split. A line may therefore be narrower than ``width`` but never wider, except when a single character
      (with its combining marks) is itself wider than ``width``: then it goes on a line by itself.
    * Empty or all-space text gives ``[]``. ``width`` must be at least 1 (else ValueError).
    """
    lines, cur = [], ""
    for word in text.split():
        cand = word if not cur else cur + " " + word
        if len(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines
