"""Build the Product Hunt gallery (tasks RB5b, rebuilt in RB5e): brand/launch/ph-1.png to ph-5.png at 1270x760, the
five shots brand/launch/producthunt.md lists under "Gallery".

John's brief for the rebuild (2026-11-12, after rejecting the paper-white set): no paper-white slides with
half-empty terminal windows; one big headline readable at thumbnail size; the terminal cropped tight and enlarged
to fill the frame; strong brand-colour use. So every image is Record red, the headline is Bricolage Grotesque 800
at 72 px in Leader, and the terminal is a full-bleed Spool band sized to its text, at the largest mono size that
fits (each shot its own size, never under MONO_MIN). Shot 1 is logo E (John's pick) in its one-colour version,
since its red cursor would vanish on a red ground.

Nothing here is typed from memory. The terminal shots (2 to 4) are beats of the recorded demo session,
brand/demo/manifest.json, which tests/test_demo.py replays against the real CLI byte for byte: the command, the
lines it printed, and the beat's own comment as the headline. Shot 2 shows the end of the replay list from step
REPLAY_FROM on; the steps above it are folded into a row of tick marks, one per hidden step (the step ruler
motif), so nothing is cut silently. Shot 5's commands are README sh lines, its headline is the start of
producthunt.md's gallery item 5, and its notes are README sentences. build() refuses to draw a line it cannot
find in its source; tests/test_gallery.py checks gallery.json against the same sources and reads each PNG's size
and colours from the file.

Usage: .venv/bin/python brand/launch/gallery.py [<.brandcache dir>]
Needs what brand/vsl/render.py needs (fontTools in .venv; @fontsource packages and @resvg/resvg-js in
.brandcache; node). Writes brand/launch/ph-1.png .. ph-5.png, brand/launch/gallery.json and
brand/launch/gallery-sheet.png. SVG sources go to build/gallery/ (git-ignored).
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


render = load("gallery_vsl_render", os.path.join(BRAND, "vsl", "render.py"))
C = render.C

W, H = 1270, 760                 # Product Hunt's recommended gallery size (tests/test_launch.py PH_GALLERY)
GROUND = "Record"                # John's brief: strong brand colour, no paper-white
M = 56                           # left/right margin of every text block (the bands bleed past it to the edges)
render.SAFE = 40                 # this module's own copy of render.py, so the VSLs keep their 60
HEAD = 72                        # headline: Bricolage Grotesque 800, at most two lines
HEAD_LH = 78
HEAD_LINES = 2
BLOCK_TOP = 250                  # every terminal shot's first band starts here (review RB5e round 1: one rhythm)
MONO_MIN, MONO_MAX = 24, 40      # terminal text: the largest size that fits each shot, on a half-pixel grid
PAD = 30                         # least band padding above and below the text
PAD_MAX = 52                     # a band shorter than its room grows its padding and leading up to these
LEAD, LEAD_MAX = 1.36, 1.9       # line height as a multiple of the mono size: natural, and the most it grows to
LABEL = 30                       # step labels over a band (ph-5): Hanken Grotesk 600
NOTE = 30                        # notes under the bands (ph-5): Hanken Grotesk 400
CREDIT_SIZE = 18
CREDIT_BASE = H - render.SAFE
REGION_BOTTOM = CREDIT_BASE - CREDIT_SIZE - 28   # bands and notes end above the credit
REPLAY_FROM = 10                 # ph-2 shows the replay list from this step on
STEP_LABELS = ("From the repository", "In the project")     # phrases of producthunt.md gallery item 5
CREDIT = render.vsl.CREDIT       # "made by John B Joseph", BRAND.md
PROMISE = render.vsl.PROMISE     # BRAND.md one-line promise, verbatim
README_NOTES = ("Not on PyPI yet.", "No dependencies beyond the standard library.")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def readme_sh_lines():
    """[(command, comment or "")] for every line of every ```sh block in README.md."""
    out = []
    for block in re.findall(r"```sh\n(.*?)```", read("README.md"), re.S):
        for line in block.split("\n"):
            m = re.match(r"^(.*?)(\s+#\s*(.*))?$", line)
            if m.group(1).strip():
                out.append((m.group(1).strip(), (m.group(3) or "").strip()))
    return out


def gallery_items():
    """producthunt.md's numbered gallery list: {1: text, ...}."""
    body = read("brand", "launch", "producthunt.md").split("## Gallery", 1)[1].split("\n## ", 1)[0]
    return {int(n): t.strip() for n, t in re.findall(r"^(\d)\. (.+)$", body, re.M)}


def headline_of(caption, cut=None):
    """The beat's comment as a sentence-case headline; `cut` keeps the part before it (only what the terminal
    under it shows)."""
    text = caption[2:] if caption.startswith("# ") else caption
    if cut:
        text = text.split(cut, 1)[0]
    return text[0].upper() + text[1:]


def output_rows(beat, accent, start=0):
    lines = beat["output"].rstrip("\n").split("\n")
    return [[[t, "Rewind" if i in accent else "Leader"]] for i, t in enumerate(lines) if i >= start]


def command_row(cmd, comment=""):
    row = [["$ ", "Playhead"], [cmd, "Leader"]]
    if comment:
        row.append(["  # " + comment, "Playhead"])
    return row


def shots():
    """The five shots as data: what each shows and where every line came from."""
    m = json.loads(read("brand", "demo", "manifest.json"))
    by_cmd = {}
    for i, b in enumerate(m["beats"]):
        by_cmd.setdefault(b["command"], i)          # the first `git status --short` is the one after the wreck
    items = gallery_items()
    out = [{"file": "ph-1.png", "kind": "title", "item": items[1], "promise": PROMISE, "source": "BRAND.md promise"}]

    replay = m["beats"][by_cmd["rewindagents replay"]]
    lines = replay["output"].rstrip("\n").split("\n")
    skip = next(i for i, t in enumerate(lines) if re.match(r"^\s*%d\s" % REPLAY_FROM, t))
    if not all(i >= skip for i in replay["accent_rows"]):
        raise SystemExit("ph-2 would fold away a marked step")
    out.append({"file": "ph-2.png", "kind": "term", "item": items[2], "beat": by_cmd["rewindagents replay"],
                "headline": headline_of(replay["caption"], ";"),
                "panels": [{"label": None, "skipped": skip,
                            "rows": [command_row(replay["command"])]
                            + output_rows(replay, set(replay["accent_rows"]), skip)}]})

    wreck = m["beats"][by_cmd["git status --short"]]
    deleted = {i for i, t in enumerate(wreck["output"].split("\n")) if t.startswith(" D ")}
    out.append({"file": "ph-3.png", "kind": "term", "item": items[3], "beat": by_cmd["git status --short"],
                "headline": headline_of(wreck["caption"], " and "),
                "panels": [{"label": None, "skipped": 0,
                            "rows": [command_row(wreck["command"])] + output_rows(wreck, deleted)}]})

    rw = next(i for i, b in enumerate(m["beats"]) if b["command"].startswith("rewindagents rewind "))
    rewind = m["beats"][rw]
    # the one lit line is the undo line, the product's own claim (review RB5b round 1, RB5e round 1); the four
    # restored files are what the headline says
    undo = {i for i, t in enumerate(rewind["output"].split("\n")) if "undo it with: rewindagents rewind " in t}
    if len(undo) != 1:
        raise SystemExit("the rewind beat no longer prints one undo line")
    out.append({"file": "ph-4.png", "kind": "term", "item": items[4], "beat": rw,
                "headline": headline_of(rewind["caption"]),
                "panels": [{"label": None, "skipped": 0,
                            "rows": [command_row(rewind["command"])] + output_rows(rewind, undo)}]})

    sh = readme_sh_lines()
    pipx = next(c for c, _ in sh if c.startswith("pipx install "))
    install = next(c for c, _ in sh if c == "rewindagents install")
    readme = " ".join(read("README.md").split())        # sentences wrap across lines in the file
    for note in README_NOTES:
        if note not in readme:
            raise SystemExit("README.md no longer says %r" % note)
    for label in STEP_LABELS:
        if label.lower() not in items[5].lower():
            raise SystemExit("producthunt.md gallery item 5 no longer says %r" % label)
    out.append({"file": "ph-5.png", "kind": "term", "item": items[5], "headline": items[5].split(":")[0],
                "panels": [{"label": STEP_LABELS[0], "skipped": 0, "rows": [command_row(pipx)]},
                           {"label": STEP_LABELS[1], "skipped": 0,
                            "rows": [[["$ ", "Playhead"], [install, "Rewind"]]]}],   # the focal point: its own command
                "notes": list(README_NOTES)})
    return m, out


# ---- drawing ----------------------------------------------------------------------------------------------
def n_rows(panel):
    return len(panel["rows"]) + (1 if panel["skipped"] else 0)


def band_height(panel, size, pad, lh):
    return 2 * pad + (n_rows(panel) - 1) * lh + size


def headline_lines(kit, shot):
    """One line if it fits, else the two-line break with the most even line widths (no one-word orphan)."""
    words = shot["headline"].split()
    width = W - 2 * M
    if kit.disp.width(shot["headline"], HEAD, -0.02) <= width:
        return [shot["headline"]]
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa, wb = kit.disp.width(a, HEAD, -0.02), kit.disp.width(b, HEAD, -0.02)
        if max(wa, wb) <= width and (best is None or max(wa, wb) < best[0]):
            best = (max(wa, wb), [a, b])
    if best is None or HEAD_LINES < 2:
        raise SystemExit("%s: the headline does not fit %d lines" % (shot["file"], HEAD_LINES))
    return best[1]


def label_space(i):
    return LABEL + 18 if i else 0               # the first label sits above BLOCK_TOP, in the headline's gap


def block_height(shot, size, pad, lh):
    """Height from BLOCK_TOP down: bands, the labels and gaps between them, and the notes."""
    h = 0
    for i, p in enumerate(shot["panels"]):
        h += (32 if i else 0) + (label_space(i) if p["label"] else 0) + band_height(p, size, pad, lh)
    notes = shot.get("notes", [])
    return h + (30 + NOTE * 1.5 * len(notes) if notes else 0)


def fit(kit, shot):
    """The largest mono size, on a half-pixel grid, at which every line of the shot fits between the margins and
    the block fits above the credit at natural spacing; then the room left over goes into the padding and the
    leading (up to PAD_MAX and LEAD_MAX), so a band whose longest line sets its size still fills its room
    instead of leaving red void under it (review RB5e round 1). Returns (size, pad, line height)."""
    longest = max(sum(len(t) for t, _ in segs) for p in shot["panels"] for segs in p["rows"])
    room = REGION_BOTTOM - BLOCK_TOP
    size = MONO_MAX
    while (longest * kit.mono.width("x", size) > W - 2 * M
           or block_height(shot, size, PAD, round(size * LEAD)) > room):
        size -= 0.5
        if size < MONO_MIN:
            raise SystemExit("%s does not fit at %d px mono" % (shot["file"], MONO_MIN))
    pad, lh = PAD, round(size * LEAD)
    while True:
        npad, nlh = min(PAD_MAX, pad + 1), min(round(size * LEAD_MAX), lh + 1)
        if (npad, nlh) == (pad, lh) or block_height(shot, size, npad, nlh) > room:
            return size, pad, lh
        pad, lh = npad, nlh


def draw_band(cv, kit, y, panel, size, pad, lh):
    """A full-bleed Spool band (the terminal cropped to its text): the rows from the top, the folded steps as one
    row of Rule ticks after the command; returns its bottom edge and pixel points a test can sample."""
    h = band_height(panel, size, pad, lh)
    cv.add(render.rect(0, y, W, h, C["Spool"]))
    adv = kit.mono.width("x", size)
    base = y + pad + kit.mono.cap(size)
    pts = [[4, int(y + h / 2), "Spool"], [W - 4, int(y + h / 2), "Spool"]]
    for r, segs in enumerate(panel["rows"]):
        cx = M
        for text, colour in segs:
            cv.text(kit.mono, text, size, cx, base, colour)
            cx += adv * len(text)
        if cx > W - M + 0.5:
            raise SystemExit("line runs past the right margin: %r" % "".join(t for t, _ in segs))
        base += lh
        if r == 0 and panel["skipped"]:
            # one tick per folded step, a column apart, under the step numbers' column
            th = kit.mono.cap(size)
            for i in range(panel["skipped"]):
                tx = M + adv * (2 + 1.5 * i)
                cv.add(render.rect(tx, base - th, 4, th, C["Rule"]))
            pts.append([int(M + adv * 2 + 2), int(base - th / 2), "Rule"])
            base += lh
    return y + h, pts


def draw_credit(cv, kit):
    cv.text(kit.body, CREDIT, CREDIT_SIZE, M, CREDIT_BASE, "Leader")


def draw_title(cv, kit, shot):
    """Logo E in its one-colour version (Leader) over the name, the promise under it, the block on the optical
    centre, left aligned with every other shot's margin."""
    lg = kit.logo
    k = 21.6                                    # the mark 302 px wide (review RB5e round 1: 20% up from 18)
    mono = {"ink": C["Leader"], "head": C["Leader"], "ground": C[GROUND]}
    nsize = 168
    psize = 46
    plines = render.wrap(kit.body, shot["promise"], psize, W - 2 * M)
    name_cap = kit.disp.cap(nsize)
    block = lg.MARK_H * k + 56 + name_cap + 64 + kit.body.cap(psize) + (len(plines) - 1) * psize * 1.3
    top = (H - block) / 2 - 16
    x = M - 1 * k                               # the '<' apex (grid x 1) on the margin
    cv.add(lg.place(lg.mark_shapes(mono, C["Leader"]), x, top, k))
    base = top + lg.MARK_H * k + 56 + name_cap
    cv.text(kit.disp, "rewindagents", nsize, M - 6, base, "Leader", tracking=-0.02)
    base += 64 + kit.body.cap(psize)
    for line in plines:
        cv.text(kit.body, line, psize, M, base, "Leader")
        base += psize * 1.3
    draw_credit(cv, kit)
    return lg.samples(lg.MARK_SAMPLES, mono, x, top, k) + [[8, 8, GROUND], [W - 8, H - 8, GROUND]]


def draw_term(cv, kit, shot):
    size, pad, lh = fit(kit, shot)
    shot["mono_px"] = size
    shot["headline_px"] = HEAD
    lines = headline_lines(kit, shot)
    shot["headline_lines"] = lines
    base = M + kit.disp.cap(HEAD)
    for line in lines:
        cv.text(kit.disp, line, HEAD, M, base, "Leader", tracking=-0.02)
        base += HEAD_LH
    if base - HEAD_LH + 0.25 * HEAD > BLOCK_TOP - (LABEL + 18 if shot["panels"][0]["label"] else 0):
        raise SystemExit("%s: the headline runs into the first band" % shot["file"])
    y, pts = BLOCK_TOP, []
    for i, p in enumerate(shot["panels"]):
        y += 32 if i else 0
        if p["label"]:
            ly = y - LABEL - 18 if i == 0 else y      # the first label sits above BLOCK_TOP
            cv.text(kit.bold, p["label"], LABEL, M, ly + kit.bold.cap(LABEL), "Leader")
            y += label_space(i)
        y, more = draw_band(cv, kit, y, p, size, pad, lh)
        pts += more
    y += 30 if shot.get("notes") else 0
    for note in shot.get("notes", []):
        cv.text(kit.body, note, NOTE, M, y + kit.body.cap(NOTE), "Leader")
        y += NOTE * 1.5
    draw_credit(cv, kit)
    return pts + [[8, 8, GROUND], [W - 8, H - 8, GROUND]]


def build(cache):
    m, plan = shots()
    kit = render.Kit(cache)
    sdir = os.path.join(ROOT, "build", "gallery")
    shutil.rmtree(sdir, ignore_errors=True)
    os.makedirs(sdir)
    palette = {v.upper() for v in C.values()}
    names = []
    for shot in plan:
        cv = render.Canvas(W, H, GROUND)
        shot["samples"] = draw_title(cv, kit, shot) if shot["kind"] == "title" else draw_term(cv, kit, shot)
        svg = cv.svg()
        off = {f.upper() for f in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg)} - palette
        if off:
            raise SystemExit("%s uses colours outside the palette: %s" % (shot["file"], sorted(off)))
        names.append(shot["file"][:-4] + ".svg")
        with open(os.path.join(sdir, names[-1]), "w", encoding="utf-8") as f:
            f.write(svg)
    with open(os.path.join(sdir, "frames.json"), "w", encoding="utf-8") as f:
        json.dump({"width": W, "height": H, "svgs": names}, f)
    mods = os.path.join(cache, "node_modules")
    subprocess.run(["node", os.path.join(BRAND, "vsl", "render.mjs"), sdir, mods], check=True)
    for shot in plan:
        dst = os.path.join(HERE, shot["file"])
        shutil.copyfile(os.path.join(sdir, shot["file"]), dst)
        with open(dst, "rb") as f:
            shot["sha256"] = hashlib.sha256(f.read()).hexdigest()
    sheet_dir = os.path.join(sdir, "sheet")
    os.makedirs(sheet_dir)
    for shot in plan:
        shutil.copyfile(os.path.join(HERE, shot["file"]), os.path.join(sheet_dir, shot["file"]))
    subprocess.run(["node", os.path.join(BRAND, "vsl", "sheet.mjs"), sheet_dir, os.path.join(HERE, "gallery-sheet.png"),
                    mods], check=True)
    manifest = {
        "width": W, "height": H, "ground": GROUND,
        "demo_beats_sha256": hashlib.sha256(json.dumps(m["beats"], sort_keys=True).encode("utf-8")).hexdigest(),
        "note": "Written by brand/launch/gallery.py from brand/demo/manifest.json, README.md, BRAND.md's promise and "
                "producthunt.md's gallery list. Edit those, then rebuild; never edit this file or the PNGs.",
        "shots": plan,
    }
    with open(os.path.join(HERE, "gallery.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    for shot in plan:
        print("%s  %dx%d  mono %s  %s" % (shot["file"], W, H, shot.get("mono_px", "-"),
                                          shot.get("headline") or shot["promise"]))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".brandcache"))
