"""`rewindagents diff N [PATH ...]`: what `rewind N` would change, as a unified diff.

The "a" side is the working tree now, the "b" side is the file as `rewind N` would leave it, so applying the
diff (`git apply`, `patch -p1`) does what the rewind would do. It reads rewind.plan(), the same plan
`rewind N` and `rewind N --dry-run` act on, so diff and rewind list the same files: those to restore (a
created file shows as new, from /dev/null), those to delete (to /dev/null), and on stderr the ones the
rewind cannot put back. Reads only; writes nothing.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

from . import rewind

NO_EOL = "\\ No newline at end of file\n"


def _text(data: bytes | None) -> list[str] | None:
    """The lines of a file, or None when it is binary (a NUL byte, or not UTF-8)."""
    if data is None:
        return []
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def _mode(path: Path) -> str:
    try:
        return f"{0o100000 | (path.stat().st_mode & 0o777):o}"
    except OSError:
        return "100644"


def file_diff(rel: str, old: bytes | None, new: bytes | None, mode: str = "100644") -> str:
    """A git-style unified diff of one file. None on either side = the file does not exist on that side."""
    out = [f"diff --git a/{rel} b/{rel}\n"]
    if old is None:
        out.append(f"new file mode {mode}\n")
    elif new is None:
        out.append(f"deleted file mode {mode}\n")
    a_name = "/dev/null" if old is None else f"a/{rel}"
    b_name = "/dev/null" if new is None else f"b/{rel}"
    a, b = _text(old), _text(new)
    if a is None or b is None:
        out.append(f"Binary files {a_name} and {b_name} differ\n")
        return "".join(out)
    if not a and not b:        # an empty file created or deleted: the header says it all
        return "".join(out)
    for line in difflib.unified_diff(a, b, a_name, b_name, lineterm="\n"):
        out.append(line)
        if not line.endswith("\n"):
            out.append("\n" + NO_EOL)
    return "".join(out)


def diff(log_path: str | Path, n: int, session: str | None = None,
         paths: list[str | Path] | None = None) -> dict:
    """The plan for `rewind n` (only `paths`, when given) plus one diff per file it would change.

    p["files"] is [(path, diff text)] in the order `rewind --dry-run` prints them: restores, then deletes."""
    p = rewind.plan(log_path, n, session, only=paths or None)
    root = rewind.project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    files = []
    for path_s, sha in p["restore"]:
        path = Path(path_s)
        old = path.read_bytes() if path.is_file() else None
        files.append((path_s, file_diff(rewind.relative(path, root), old, (objects / sha).read_bytes(),
                                        _mode(path) if old is not None else "100644")))
    for path_s in p["delete"]:
        path = Path(path_s)
        files.append((path_s, file_diff(rewind.relative(path, root), path.read_bytes(), None, _mode(path))))
    p["files"] = files
    return p


def run(log_path: str | Path, n: int, session: str | None, paths: list[str] | None, out=None, err=None) -> int:
    """CLI body. The diff goes to stdout; anything rewind could not put back goes to stderr.
    Exit 2 for a step the session does not have (as every command), 0, or 1 when something could not be shown (the rewind would report it and exit 1 too) or a file
    changed after the steps the rewind takes back (p["drift"]: the rewind would refuse without --force)."""
    out, err = out or sys.stdout, err or sys.stderr
    try:
        p = diff(log_path, n, session, paths)
    except rewind.RewindError as e:
        print(f"rewindagents: {e}", file=err)
        return 2 if isinstance(e, rewind.StepRangeError) else 1
    root = rewind.project_root(log_path)
    for _, text in p["files"]:
        out.write(text)
    for path_s, why in p["cannot"]:
        print(f"rewindagents: CANNOT {rewind.relative(path_s, root)}: {why}", file=err)
    for q in p["unmatched"]:
        print(f"rewindagents: {q}: no step after step {n} changed it", file=err)
    for d in p.get("drift") or []:
        print(f"rewindagents: WARNING {rewind.relative(d['path'], root)}: {rewind.drift_why(d)}; rewind {n} would "
              f"overwrite that, so it refuses without --force", file=err)
    if not p["files"] and not p["cannot"]:
        print(f"rewindagents: rewind {n} would change nothing (session {p['session']})", file=err)
    if p["bash_uncovered"]:
        print(f"rewindagents: note: {p['bash_uncovered']} step(s) after step {n} were not scanned before and "
              f"after; files they changed are not in this diff", file=err)
    if p["scan_early"]:
        print(f"rewindagents: note: {p['scan_early']} step(s) after step {n} ran a command in the background, "
              f"so their after-scan may have run before it finished; files it changed later may not be in this diff",
              file=err)
    return 1 if p["cannot"] or p["bash_uncovered"] or p["scan_early"] or p.get("drift") else 0


def step_changes(log_path: str | Path, all_steps: list[dict], n: int, redact: bool = False) -> list[dict]:
    """What step n itself did to each file it checkpointed: the bytes right before the step (its checkpoint)
    against the bytes right after it (the next checkpoint of that file in the session, else the file now), the
    same before/after the export page diffs. One entry per file: path, kind (changed, created, deleted,
    unchanged or unknown), the diff text, and why when it cannot be shown. With redact, secrets in both sides
    are replaced first (as export does) and entry["redacted"] counts them."""
    from .export import _after, _read_object      # one definition of "right after the step" for both
    from . import redact as _redact
    root = rewind.project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    out = []
    for cp in all_steps[n - 1]["checkpoints"]:
        rel = rewind.relative(cp["path"], root)
        entry = {"path": rel, "kind": "unknown", "text": "", "why": "", "redacted": 0}
        if cp.get("skipped"):
            entry["why"] = f"not checkpointed before the step ({cp['skipped']})"
            out.append(entry)
            continue
        before = _read_object(objects, cp.get("sha256"))
        if cp.get("sha256") and before is None:
            entry["why"] = "the stored copy from before the step is missing"
            out.append(entry)
            continue
        after, label = _after(all_steps, n - 1, cp["path"], root, objects)
        if label.startswith("unknown"):
            entry["why"] = f"the file right after the step is {label}"
            out.append(entry)
            continue
        if before is None and after is None:
            entry["kind"] = "unchanged"         # created and removed again within the step
        elif before is None:
            entry["kind"] = "created"
        elif after is None:
            entry["kind"] = "deleted"
        else:
            entry["kind"] = "changed" if before != after else "unchanged"
        if entry["kind"] != "unchanged":
            if redact:
                env = _redact.is_env_file(rel)
                before, k1 = _redact.data(before, env)
                after, k2 = _redact.data(after, env)
                entry["redacted"] = k1 + k2
                if entry["kind"] == "changed" and before == after:
                    entry["why"] = "changed only inside redacted values"
            entry["text"] = file_diff(rel, before, after) if before != after or entry["kind"] != "changed" else ""
        out.append(entry)
    return out


def step_run(log_path: str | Path, all_steps: list[dict], n: int, root: Path, out=None, err=None,
             redact: bool = False) -> int:
    """`replay --step N --diff`: one line per file (changed, created, deleted), then the diffs, git-style, so
    applying them in reverse undoes exactly this step. Exit 1 when some file's change cannot be shown.
    With redact (replay's default), secrets are replaced in the summary and in both sides of every diff, as
    `export` does; a diff with redacted values cannot be applied as it is."""
    from . import redact as _redact
    out, err = out or sys.stdout, err or sys.stderr
    s = all_steps[n - 1]
    changes = step_changes(log_path, all_steps, n, redact=redact)
    line, k = rewind.summary(s, width=sys.maxsize, root=root), 0
    if redact:
        line, k = _redact.text(line)
    line = line if len(line) <= 80 else line[:77] + "..."
    print(f"step {n}  {s['tool']}  {line}", file=out)
    if redact:
        redaction_note(k + sum(c["redacted"] for c in changes), err)
    if not changes:
        why = "it changed no file" if s.get("scanned") or s["tool"] in rewind.FILE_TOOLS else \
            "nothing was checkpointed for it (a tool that does not change files)"
        print(f"  no file changes recorded: {why}", file=out)
        return 0
    for c in changes:
        print(f"  {c['kind']:<9} {c['path']}" + (f"  ({c['why']})" if c["why"] else ""), file=out)
    for c in changes:
        if c["text"]:
            out.write(c["text"])
    if any(c["kind"] == "unknown" for c in changes):
        print("rewindagents: some of this step's changes cannot be shown; see the lines marked unknown", file=err)
        return 1
    return 0


def redaction_note(n: int, err) -> None:
    """replay's line on stderr when it replaced secrets: how many, and how to see them."""
    if n:
        print(f"rewindagents: {n} secret value{'s' if n != 1 else ''} replaced with [redacted ...]; "
              f"--no-redact shows them", file=err)
