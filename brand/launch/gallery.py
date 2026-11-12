"""Build the Product Hunt gallery (task RB5b): brand/launch/ph-1.png to ph-5.png at 1270x760, the five shots
brand/launch/producthunt.md lists under "Gallery".

Nothing here is typed from memory. The terminal shots (2 to 4) are beats of the recorded demo session,
brand/demo/manifest.json, which tests/test_demo.py replays against the real CLI byte for byte: the command, every
line it printed, and the beat's own comment as the headline. Shot 5's commands are README sh lines (the comment
beside `rewindagent install` is the README's), its headline is the start of producthunt.md's gallery item 5, and
its notes are README sentences. Shot 1 is the wordmark and BRAND.md's one-line promise. build() refuses to draw a
line it cannot find in its source; tests/test_gallery.py checks gallery.json against the same sources and reads
each PNG's size and colours from the file.

Look (BRAND.md): Leader paper, Reel headline in Bricolage Grotesque 800, a Spool terminal with the mono mark in
its title bar, Leader text, Playhead for the prompt and comments, Rewind for the one block to look at (the two
steps that wrecked the repo, the two deleted tests, the four restored files). Shot 1's one accent is the mark's
Record playhead. The credit closes every image in Tape. Text is outlined from the OFL font files.

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
M = 48                           # margin: no text closer to an edge (a gallery image is not cropped like a feed)
render.SAFE = M                  # this module's own copy of render.py, so the VSLs keep their 60
HEAD = 36                        # headline: Bricolage Grotesque 800, one line
MONO_MIN, MONO_MAX = 20, 34     # terminal text: ONE size for every shot, the largest that fits them all
PAD = 24                         # terminal padding
PANEL_TOP = M + 26 + 40          # every terminal starts here (one-line headline above it)
REGION_BOTTOM = H - M - 16 - 28  # and ends above the credit
NOTE = 22                        # notes under a panel: Hanken Grotesk 400, smaller than the labels
LABEL = 26                       # step labels over a panel: Hanken Grotesk 600
STEP_LABELS = ("From the repository", "In the project")     # phrases of producthunt.md gallery item 5
CREDIT_SIZE = 16
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
    """The beat's comment as a sentence-case headline; `cut` keeps the part before it (review round 1: one line,
    and only what the terminal under it shows)."""
    text = caption[2:] if caption.startswith("# ") else caption
    if cut:
        text = text.split(cut, 1)[0]
    return text[0].upper() + text[1:]


def output_rows(beat, accent):
    lines = beat["output"].rstrip("\n").split("\n")
    return [[[t, "Rewind" if i in accent else "Leader"]] for i, t in enumerate(lines)]


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

    replay = m["beats"][by_cmd["rewindagent replay"]]
    out.append({"file": "ph-2.png", "kind": "term", "item": items[2], "beat": by_cmd["rewindagent replay"],
                "headline": headline_of(replay["caption"], ";"),
                "rows": [command_row(replay["command"])] + output_rows(replay, set(replay["accent_rows"]))})

    wreck = m["beats"][by_cmd["git status --short"]]
    deleted = {i for i, t in enumerate(wreck["output"].split("\n")) if t.startswith(" D ")}
    out.append({"file": "ph-3.png", "kind": "term", "item": items[3], "beat": by_cmd["git status --short"],
                "headline": headline_of(wreck["caption"], " and "),
                "rows": [command_row(wreck["command"])] + output_rows(wreck, deleted)})

    rw = next(i for i, b in enumerate(m["beats"]) if b["command"].startswith("rewindagent rewind "))
    rewind = m["beats"][rw]
    out.append({"file": "ph-4.png", "kind": "term", "item": items[4], "beat": rw,
                "headline": headline_of(rewind["caption"]),
                "rows": [command_row(rewind["command"])] + output_rows(rewind, set(rewind["accent_rows"]))})

    sh = readme_sh_lines()
    pipx = next(c for c, _ in sh if c.startswith("pipx install "))
    install = next((c, n) for c, n in sh if c == "rewindagent install")
    readme = " ".join(read("README.md").split())        # sentences wrap across lines in the file
    for note in README_NOTES:
        if note not in readme:
            raise SystemExit("README.md no longer says %r" % note)
    for label in STEP_LABELS:
        if label.lower() not in items[5].lower():
            raise SystemExit("producthunt.md gallery item 5 no longer says %r" % label)
    out.append({"file": "ph-5.png", "kind": "term", "item": items[5], "headline": items[5].split(":")[0],
                "panels": [{"label": STEP_LABELS[0], "rows": [command_row(pipx)]},
                           {"label": STEP_LABELS[1], "rows": [command_row(*install)]}],
                "notes": list(README_NOTES)})
    for shot in out[1:4]:
        shot["panels"] = [{"label": None, "rows": shot.pop("rows")}]
    return m, out


# ---- drawing ----------------------------------------------------------------------------------------------
def line_height(size):
    return round(size * 1.36)


def panel_height(n, size):
    return 2 * PAD + n * line_height(size) - (line_height(size) - size)


def draw_panel(cv, kit, x, y, w, rows, size, min_h=0):
    """A Spool terminal (no title bar: review round 1), text from the top like a real one; returns its bottom
    edge and the pixel points (x, y, palette name) a test can sample."""
    h = max(min_h, panel_height(len(rows), size))
    cv.add(render.rect(x, y, w, h, C["Spool"]))
    adv = kit.mono.width("x", size)
    cols = int((w - 2 * PAD) // adv)
    base = y + PAD + kit.mono.cap(size)
    for segs in rows:
        cx = x + PAD
        for text, colour in segs:
            if len(text) > cols:
                raise SystemExit("line of %d characters does not fit %d columns: %r" % (len(text), cols, text))
            cv.text(kit.mono, text, size, cx, base, colour)
            cx += adv * len(text)
        base += line_height(size)
    return y + h, [[int(x + 6), int(y + 6), "Spool"], [int(x + w - 6), int(y + h - 6), "Spool"]]


def block_height(shot, size):
    """Height of everything under the headline: step labels, panels, the gaps between them and the notes."""
    h = 0
    for i, p in enumerate(shot["panels"]):
        h += (40 if i else 0) + (LABEL + 18 if p["label"] else 0) + panel_height(len(p["rows"]), size)
    notes = shot.get("notes", [])
    return h + (28 + NOTE * 1.5 * len(notes) if notes else 0)


def fit_size(kit, plan):
    """ONE terminal size for the whole set (review round 1): the largest, on a half-pixel grid, at which every
    line of every shot fits the panel width with a right margin of at least PAD, and every shot fits its height."""
    terms = [s for s in plan if s["kind"] == "term"]
    longest = max(sum(len(t) for t, _ in segs) for s in terms for p in s["panels"] for segs in p["rows"])
    size = MONO_MAX
    while size > MONO_MIN and (longest * kit.mono.width("x", size) > W - 2 * M - 2 * PAD
                               or any(block_height(s, size) > REGION_BOTTOM - PANEL_TOP for s in terms)):
        size -= 0.5
    return size


def draw_credit(cv, kit):
    cv.text(kit.body, CREDIT, CREDIT_SIZE, M, H - M, "Tape")


def draw_title(cv, kit, shot):
    """The stacked lockup (as logo-light.png: the mark over the name, review round 1 asked for a bigger mark
    without changing its geometry), the promise under it, the block a little above centre."""
    lg = kit.logo
    k = 13.0                                    # the 16-unit mark at 208 px wide
    nsize = 132
    psize = 40
    name_cap = kit.disp.cap(nsize)
    block = lg.MARK_H * k + 44 + name_cap + 72 + kit.body.cap(psize)
    top = (H - block) / 2 - 20
    x = M + 16
    cv.add(lg.place(lg.mark_shapes(lg.THEMES["light"]), x, top, k))
    base = top + lg.MARK_H * k + 44 + name_cap
    cv.text(kit.disp, "rewindagent", nsize, x - 4, base, "Reel", tracking=-0.02)
    cv.text(kit.body, shot["promise"], psize, x, base + 72 + kit.body.cap(psize), "Reel")
    draw_credit(cv, kit)
    # the playhead's head (grid 9, 4.5) and the paper
    return [[int(x + 9 * k), int(top + (4.5 - lg.MARK_TOP) * k), "Record"], [8, 8, "Leader"], [W - 8, H - 8, "Leader"]]


def draw_term(cv, kit, shot, size):
    lines = render.wrap(kit.disp, shot["headline"], HEAD, W - 2 * M)
    if len(lines) != 1:
        raise SystemExit("%s: the headline takes %d lines; every terminal must start at the same height"
                         % (shot["file"], len(lines)))
    cv.text(kit.disp, shot["headline"], HEAD, M, M + kit.disp.cap(HEAD), "Reel", tracking=-0.02)
    shot["mono_px"] = size
    y, pts = PANEL_TOP, []
    single = len(shot["panels"]) == 1 and not shot.get("notes")
    for i, p in enumerate(shot["panels"]):
        y += 40 if i else 0
        if p["label"]:
            cv.text(kit.bold, p["label"], LABEL, M, y + kit.bold.cap(LABEL), "Reel")
            y += LABEL + 18
        # one terminal window, the same size in every shot that has one; ph-5's two steps fit their lines
        y, more = draw_panel(cv, kit, M, y, W - 2 * M, p["rows"], size,
                             REGION_BOTTOM - PANEL_TOP if single else 0)
        pts += more
    y += 28 if shot.get("notes") else 0
    for note in shot.get("notes", []):
        cv.text(kit.body, note, NOTE, M, y + kit.body.cap(NOTE), "Tape")
        y += NOTE * 1.5
    draw_credit(cv, kit)
    return pts + [[8, 8, "Leader"], [W - 8, H - 8, "Leader"]]


def build(cache):
    m, plan = shots()
    kit = render.Kit(cache)
    sdir = os.path.join(ROOT, "build", "gallery")
    shutil.rmtree(sdir, ignore_errors=True)
    os.makedirs(sdir)
    palette = {v.upper() for v in C.values()}
    size = fit_size(kit, plan)
    names = []
    for shot in plan:
        cv = render.Canvas(W, H, "Leader")
        shot["samples"] = draw_title(cv, kit, shot) if shot["kind"] == "title" else draw_term(cv, kit, shot, size)
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
        "width": W, "height": H,
        "demo_beats_sha256": hashlib.sha256(json.dumps(m["beats"], sort_keys=True).encode("utf-8")).hexdigest(),
        "note": "Written by brand/launch/gallery.py from brand/demo/manifest.json, README.md, BRAND.md's promise and "
                "producthunt.md's gallery list. Edit those, then rebuild; never edit this file or the PNGs.",
        "shots": plan,
    }
    with open(os.path.join(HERE, "gallery.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    for shot in plan:
        print("%s  %dx%d  %s" % (shot["file"], W, H, shot.get("headline") or shot["promise"]))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".brandcache"))
