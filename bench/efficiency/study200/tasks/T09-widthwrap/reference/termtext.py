"""Lay out text for a fixed-width terminal."""
import unicodedata


def char_width(c):
    if c == "‍" or unicodedata.combining(c):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def text_width(s):
    return sum(char_width(c) for c in s)


def _clusters(word):
    out = []
    for c in word:
        if out and char_width(c) == 0:
            out[-1] += c
        else:
            out.append(c)
    return out


def _break(word, width):
    pieces, cur = [], ""
    for cl in _clusters(word):
        if cur and text_width(cur) + text_width(cl) > width:
            pieces.append(cur)
            cur = ""
        cur += cl
    if cur:
        pieces.append(cur)
    return pieces


def wrap(text, width):
    if width < 1:
        raise ValueError("width must be at least 1")
    lines, cur = [], ""
    for word in text.split(" "):
        if not word:
            continue
        for piece in (_break(word, width) if text_width(word) > width else [word]):
            cand = piece if not cur else cur + " " + piece
            if text_width(cand) <= width:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = piece
    if cur:
        lines.append(cur)
    return lines


def pad(text, width, align="left"):
    if align not in ("left", "right", "center"):
        raise ValueError("align must be left, right or center")
    extra = width - text_width(text)
    if extra <= 0:
        return text
    if align == "left":
        return text + " " * extra
    if align == "right":
        return " " * extra + text
    return " " * (extra // 2) + text + " " * (extra - extra // 2)
