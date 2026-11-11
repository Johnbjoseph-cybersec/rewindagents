"""Read a GIF's size, frame count, total play time, frame delays, loop flag and colour table with the
standard library.

Used by brand/demo/build.py after it writes brand/demo.gif, and by tests/test_demo.py, so the "under
20 seconds" rule and the palette are checked on the file itself, not on the tables that produced it.
"""
import struct


def _skip_sub_blocks(data, i):
    while True:
        n = data[i]
        i += 1
        if n == 0:
            return i
        i += n


def info(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:6] not in (b"GIF89a", b"GIF87a"):
        raise ValueError("not a GIF: %r" % data[:6])
    width, height, packed = struct.unpack("<HHB", data[6:11])
    i = 13
    colors = []
    if packed & 0x80:                       # global colour table
        n = 2 << (packed & 0x07)
        colors = ["#%02X%02X%02X" % tuple(data[i + 3 * j:i + 3 * j + 3]) for j in range(n)]
        i += 3 * n
    frames, centiseconds, loops, delays = 0, 0, None, set()
    while i < len(data):
        b = data[i]
        if b == 0x3B:                       # trailer
            break
        if b == 0x21:                       # extension
            label = data[i + 1]
            i += 2
            if label == 0xF9:               # graphic control: block size, packed, delay (cs), transparent index
                d = struct.unpack("<H", data[i + 2:i + 4])[0]
                centiseconds += d
                delays.add(d)
            elif label == 0xFF and data[i + 1:i + 12] == b"NETSCAPE2.0":
                loops = struct.unpack("<H", data[i + 14:i + 16])[0]   # 0 = forever
            i = _skip_sub_blocks(data, i)
        elif b == 0x2C:                     # image descriptor
            lpacked = data[i + 9]
            i += 10
            if lpacked & 0x80:
                i += 3 * (2 << (lpacked & 0x07))
            i += 1                          # LZW minimum code size
            i = _skip_sub_blocks(data, i)
            frames += 1
        else:
            raise ValueError("unexpected block 0x%02x at %d" % (b, i))
    return {"width": width, "height": height, "frames": frames, "seconds": centiseconds / 100.0,
            "loops": loops, "delays_cs": sorted(delays), "colors": colors}


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(info(sys.argv[1])))
