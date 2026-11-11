#!/usr/bin/env python3
"""Measure palette fidelity: read pixels out of the rendered PNGs at the sample points build.py wrote into
manifest.json and compare each with the BRAND.md hex for the palette name expected there.

Stdlib only (zlib + the PNG filters), so tests/test_logo.py can run the same check. Prints one line per
sample and exits 1 on any mismatch. Usage: python3 brand/logo/pngsample.py
"""
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
sys.path.insert(0, BRAND)
from contrast_check import PALETTE  # noqa: E402

_cache = {}


def load_png(path, rows_needed=None):
    """Decode an 8-bit, non-interlaced PNG. Returns (width, height, bytes per pixel, rows)."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    pos, idat, hdr = 8, [], None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat.append(body)
        pos += 12 + ln
    w, h, depth, ctype, _, _, interlace = hdr
    assert depth == 8 and interlace == 0, "%s: only 8-bit non-interlaced PNGs" % path
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    prev = bytearray(stride)
    rows = []
    i = 0
    for _ in range(h if rows_needed is None else min(h, rows_needed)):
        ftype = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ftype == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif ftype == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif ftype == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif ftype == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 255
        rows.append(bytes(line))
        prev = line
    return w, h, bpp, rows


def pixel(path, x, y, rows_needed=None):
    """'#RRGGBB' at (x, y), composited over nothing (alpha ignored; the brand PNGs are opaque)."""
    if path not in _cache:
        _cache[path] = load_png(path, rows_needed)
    w, h, bpp, rows = _cache[path]
    if y >= len(rows):  # a deeper row than the first call needed: decode again
        _cache[path] = load_png(path, None)
        w, h, bpp, rows = _cache[path]
    assert 0 <= x < w and 0 <= y < h, (path, x, y)
    px = rows[y][x * bpp:x * bpp + bpp]
    if bpp == 1:
        return "#%02X%02X%02X" % (px[0], px[0], px[0])
    return "#%02X%02X%02X" % (px[0], px[1], px[2])


def check(manifest_path=os.path.join(HERE, "manifest.json")):
    """Yield (png, x, y, expected name, expected hex, got hex, ok) for every sample in the manifest."""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    for png in sorted(manifest):
        pts = manifest[png].get("samples", [])
        deepest = max((p[1] for p in pts), default=0) + 1
        for x, y, name in pts:
            want = PALETTE[name].upper()
            got = pixel(os.path.join(BRAND, png), x, y, rows_needed=deepest)
            yield png, x, y, name, want, got, got == want


def main():
    bad = 0
    print("%-28s %5s %5s %-9s %-8s %-8s %s" % ("png", "x", "y", "expect", "BRAND.md", "sampled", "result"))
    for png, x, y, name, want, got, ok in check():
        bad += 0 if ok else 1
        print("%-28s %5d %5d %-9s %-8s %-8s %s" % (png, x, y, name, want, got, "ok" if ok else "MISMATCH"))
    print("%d mismatches" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
