"""Read the facts a test needs from an MP4 file with the standard library only (task RB4b): duration, the video
track's size, codec and frame rate, and the audio track's codec, sample rate and channel count. Walks the ISO
BMFF boxes (moov > mvhd, trak > tkhd, mdia > mdhd / hdlr / minf > stbl > stsd / stts). Enough for files ffmpeg
writes; not a general parser.

  python3 brand/vsl/mp4info.py brand/vsl-90s.mp4
"""
import json
import struct
import sys

CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}


def boxes(data, start, end):
    """(type, payload start, box end) for every box in data[start:end]."""
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        head = 8
        if size == 1:
            size = struct.unpack(">Q", data[i + 8:i + 16])[0]
            head = 16
        elif size == 0:
            size = end - i
        if size < head:
            raise ValueError("bad box size at %d" % i)
        yield kind, i + head, i + size
        i += size


def find(data, start, end, path):
    for kind, s, e in boxes(data, start, end):
        if kind == path[0]:
            if len(path) == 1:
                return s, e
            return find(data, s, e, path[1:])
    return None


def full(data, s):
    """Version of a full box and the offset after its version+flags."""
    return data[s], s + 4


def track(data, s, e):
    t = {}
    hd = find(data, s, e, [b"mdia", b"hdlr"])
    t["handler"] = data[hd[0] + 8:hd[0] + 12].decode("ascii")
    md = find(data, s, e, [b"mdia", b"mdhd"])
    v, o = full(data, md[0])
    if v == 1:
        scale, dur = struct.unpack(">IQ", data[o + 16:o + 28])
    else:
        scale, dur = struct.unpack(">II", data[o + 8:o + 16])
    t["timescale"], t["duration"] = scale, dur
    sd = find(data, s, e, [b"mdia", b"minf", b"stbl", b"stsd"])
    _, o = full(data, sd[0])
    entry = o + 4                                  # entry count, then the first sample entry box
    t["codec"] = data[entry + 4:entry + 8].decode("ascii")
    body = entry + 8 + 8                           # reserved(6) + data_reference_index(2)
    if t["handler"] == "vide":
        t["width"], t["height"] = struct.unpack(">HH", data[body + 16:body + 20])
        st = find(data, s, e, [b"mdia", b"minf", b"stbl", b"stts"])
        _, o = full(data, st[0])
        (n,) = struct.unpack(">I", data[o:o + 4])
        runs = [struct.unpack(">II", data[o + 4 + 8 * k:o + 12 + 8 * k]) for k in range(n)]
        t["samples"] = sum(c for c, _ in runs)
        t["deltas"] = sorted({d for _, d in runs})
    elif t["handler"] == "soun":
        t["channels"], = struct.unpack(">H", data[body + 8:body + 10])
        t["sample_rate"] = struct.unpack(">I", data[body + 16:body + 20])[0] >> 16
    return t


def info(path):
    with open(path, "rb") as f:
        data = f.read()
    moov = find(data, 0, len(data), [b"moov"])
    if not moov:
        raise ValueError("no moov box: not an MP4 file")
    mv = find(data, moov[0], moov[1], [b"mvhd"])
    v, o = full(data, mv[0])
    if v == 1:
        scale, dur = struct.unpack(">IQ", data[o + 16:o + 28])
    else:
        scale, dur = struct.unpack(">II", data[o + 8:o + 16])
    out = {"seconds": round(dur / scale, 3), "faststart": data.find(b"moov") < data.find(b"mdat")}
    for kind, s, e in boxes(data, moov[0], moov[1]):
        if kind != b"trak":
            continue
        t = track(data, s, e)
        if t["handler"] == "vide":
            out.update(width=t["width"], height=t["height"], video_codec=t["codec"], frames=t["samples"],
                       video_seconds=round(t["duration"] / t["timescale"], 3))
            if len(t["deltas"]) == 1:
                out["fps"] = round(t["timescale"] / t["deltas"][0], 3)
            else:
                out["fps"] = None                  # variable frame rate
        elif t["handler"] == "soun":
            out.update(audio_codec=t["codec"], sample_rate=t["sample_rate"], channels=t["channels"],
                       audio_seconds=round(t["duration"] / t["timescale"], 3))
    return out


if __name__ == "__main__":
    print(json.dumps(info(sys.argv[1]), indent=1, sort_keys=True))
