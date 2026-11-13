"""Fork a recorded session at any step into a separate run, then compare runs on what they actually did.

`fork N --name X` makes a new directory holding the project's files exactly as `rewind N` would leave them:
the project as it is now, with every change the session made after step N taken back. In a git repository it
is a `git worktree` on the branch `rewindagents/run/X`; otherwise a plain directory. The directory gets its own
`.rewindagents/` whose first record is the fork itself: the source project, session and step, the source
log's head hash at that moment, and every file of the starting point with its SHA-256 (copies kept in the
run's own store, so `gc` there keeps them and a diff from the start needs nothing outside the run). Any
agent, or a person, then continues from there; with the hook in place its steps go into the run's own log.

`compare` lines the runs up against that shared starting point: per run, which agents took how many steps,
which files it changed, created or deleted, and the lines added and removed; per file, which runs ended with
the same bytes. `--check CMD` runs a command (your tests) in each run and reports its exit code. `--diff A B`
prints how two runs differ, file by file.

Local only, like the rest: it reads and writes files and runs git and the command you name, nothing else.
The source project is never changed by `fork` except for one line in `.rewindagents/runs.json`, the list of
its runs; `compare` writes nothing (the command `--check` runs may, in the run it runs in).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from . import agents, bashscan, log, project, rewind
from .hook import MAX_CHECKPOINT_BYTES, checkpoint

INDEX = "runs.json"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CHECK_TAIL = 3            # lines of a check's output kept per run


class RunError(Exception):
    pass


# ---------------------------------------------------------------------------------------------------- fork
def start_state(log_path: str | Path, n: int, session: str | None = None) -> dict[str, tuple[str, Any]]:
    """{relative path: ("now", absolute path) | ("object", sha256)}: the project's files as `rewind n` would
    leave them. Refuses when that cannot be known exactly (what rewind would report as CANNOT or unscanned)."""
    p = rewind.plan(log_path, n, session)
    root = rewind.project_root(log_path)
    problems = [f"{rewind.relative(path, root)}: {why}" for path, why in p["cannot"]]
    if p["bash_uncovered"]:
        problems.append(f"{p['bash_uncovered']} step(s) after step {n} were not scanned before and after")
    if p["scan_early"]:
        problems.append(f"{p['scan_early']} step(s) after step {n} ran a command in the background")
    if problems:
        raise RunError("cannot rebuild the files as they were right after step %d, so a run from it would not "
                       "start where the session was: %s" % (n, "; ".join(problems)))
    rels = run_files(root)
    if rels is None:
        raise RunError(f"the project has more than {bashscan.MAX_SCAN_FILES} files; a run is not made for it")
    state: dict[str, tuple[str, Any]] = {r: ("now", root / r) for r in rels}
    for path_s, sha in p["restore"]:
        state[rewind.relative(path_s, root)] = ("object", sha)
    for path_s in p["delete"]:
        state.pop(rewind.relative(path_s, root), None)
    return dict(sorted(state.items()))


def run_files(root: Path) -> list[str] | None:
    """The project's files as the scan sees them, minus caches and environments (`__pycache__`, `.venv`,
    `node_modules`, ...: bashscan.SKIP_DIRS) even when git does not ignore them: they are build output, not
    the work, and would make every run differ from every other."""
    rels = bashscan.project_files(root)
    if rels is None:
        return None
    return [r for r in rels if not (set(Path(r).parts[:-1]) & bashscan.SKIP_DIRS)]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _git_head(root: Path) -> str | None:
    """HEAD's commit when the project is a git repository's top directory; None otherwise (no git, no commit
    yet, or a project in a subdirectory of a repository, whose worktree would hold the whole repository)."""
    top = _git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root.resolve():
        return None
    head = _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    return head.stdout.strip() if head.returncode == 0 else None


def _write(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return
    tmp = path.with_name(f".{path.name}.rewindagents.tmp")
    tmp.write_bytes(data)
    if mode is not None:
        os.chmod(tmp, mode & 0o777)
    os.replace(tmp, path)


def default_dir(root: Path, name: str) -> Path:
    """Next to the project, named like the worktrees in Claude Code's docs (`../project-feature-a`)."""
    return root.parent / f"{root.name}-{name}"


def fork(log_path: str | Path, n: int, name: str, session: str | None = None,
         dest: str | Path | None = None) -> dict:
    """Make the run directory (see the module docstring). Returns what was made, for the CLI to print."""
    if not NAME_RE.match(name or ""):
        raise RunError(f"{name!r} is not a run name: use letters, digits, '.', '_' or '-' (up to 64)")
    log_path = Path(log_path)
    root = rewind.project_root(log_path)
    session = session or rewind.latest_session(log_path)
    if session is None:
        raise RunError("the log holds no session yet")
    target = Path(os.path.abspath(dest)) if dest else default_dir(root, name)
    rt = target.resolve()
    if rt == root or root in rt.parents:
        raise RunError(f"{target} is inside the project; a run lives outside it (default: {default_dir(root, name)})")
    if target.exists():
        raise RunError(f"{target} already exists; pick another --name or --dir")
    if any(r.get("name") == name for r in read_index(root)):
        raise RunError(f"this project already has a run named {name!r} (`rewindagents compare` lists them)")
    state = start_state(log_path, n, session)
    objects = root / ".rewindagents" / "objects"

    head = _git_head(root)
    git_branch = None
    try:
        if head:
            git_branch = f"rewindagents/run/{name}"
            if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{git_branch}").returncode == 0:
                raise RunError(f"git branch {git_branch} already exists")
            made = _git(root, "worktree", "add", "-q", "-b", git_branch, str(target), head)
            if made.returncode != 0:
                raise RunError(f"git worktree add failed: {made.stderr.strip()}")
        else:
            target.mkdir(parents=True)
        # Make the directory hold exactly the starting files: drop what is not in them, write what is.
        present = run_files(target) or []
        for rel in present:
            if rel not in state:
                (target / rel).unlink()
        for rel, (kind, src) in state.items():
            if kind == "now":
                st = src.stat()
                if st.st_size > MAX_CHECKPOINT_BYTES:
                    target.joinpath(rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target / rel)
                else:
                    _write(target / rel, src.read_bytes(), st.st_mode)
            else:
                _write(target / rel, (objects / src).read_bytes())

        store = target / ".rewindagents"
        store.mkdir(exist_ok=True)
        (store / ".gitignore").write_text("*\n", encoding="utf-8")
        start = []
        for rel in state:
            cp = checkpoint(target / rel, store / "objects")
            cp["path"] = rel
            if cp.get("skipped"):           # too big to keep a copy of: keep its hash, so compare can tell
                cp["content_sha256"] = _sha_file(target / rel)
            start.append(cp)
        origin = {"name": name, "project": str(root), "session": session, "step": n,
                  "log_head": log.head(log_path), "git_branch": git_branch, "git_base": head,
                  "files": len(start)}
        log.Recorder(store / "log.jsonl").record(
            f"run:{name}", "rewindagents", {"input": {"fork": name, "from_step": n}, "fork": origin,
                                            "start": start}, None, actor="user", event="fork")
    except BaseException:
        _undo_fork(root, target, git_branch if head else None)
        raise
    entry = {"name": name, "dir": str(target), "session": session, "step": n, "created": round(time.time(), 3)}
    _append_index(root, entry)
    return {**entry, "files": len(state), "git_branch": git_branch, "hooked": hooked_agents(target),
            "project": str(root)}


def _undo_fork(root: Path, target: Path, git_branch: str | None) -> None:
    """A fork that failed half-way leaves nothing behind."""
    if git_branch:
        _git(root, "worktree", "remove", "--force", str(target))
        _git(root, "branch", "-D", git_branch)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hooked_agents(directory: Path, home: Path | None = None) -> list[str]:
    """The agents whose config (in the directory, or the user's global one) holds a rewindagents hook."""
    from . import init as setup
    from .hook import ours
    home = Path(home or Path.home())
    found = []
    for name in agents.AGENTS:
        for t in (setup.target(name, directory, home, False), setup.target(name, directory, home, True)):
            if t.is_file() and any(ours(c) for cmds in agents.commands_in(agents.AGENTS[name], t).values()
                                   for c in cmds):
                found.append(name)
                break
    return found


def read_index(root: Path) -> list[dict]:
    try:
        data = json.loads((root / ".rewindagents" / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict) and "dir" in r] if isinstance(data, list) else []


def _append_index(root: Path, entry: dict) -> None:
    entries = read_index(root) + [entry]
    p = root / ".rewindagents" / INDEX
    tmp = p.with_name(f".{INDEX}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(entries, indent=1), encoding="utf-8")
    os.replace(tmp, p)


# ------------------------------------------------------------------------------------------------- compare
def origin_of(run_dir: Path) -> tuple[dict, list[dict], float] | None:
    """(fork origin, starting files, time) from a run's first fork record, or None if it is not a run."""
    lp = run_dir / ".rewindagents" / "log.jsonl"
    if not lp.is_file():
        return None
    for rec in log.read(lp):
        args = rec.get("args") if isinstance(rec.get("args"), dict) else {}
        if rec.get("event") == "fork" and isinstance(args.get("fork"), dict):
            return args["fork"], list(args.get("start") or []), rec.get("ts", 0)
    return None


def _start_key(origin: dict, start: list[dict]) -> tuple:
    return (origin.get("project"), origin.get("session"), origin.get("step"),
            tuple(sorted((c["path"], c.get("sha256") or c.get("content_sha256")) for c in start)))


def resolve_runs(cwd: Path, names: list[str] | None) -> tuple[Path, list[tuple[str, Path]]]:
    """(the source project, [(label, directory)]). With no names: the project and every run of it that still
    exists, from the same starting point as the newest one. A name is a run name or a directory."""
    store = project.find_store_root(cwd)
    if store is None:
        raise RunError("no .rewindagents/ here or in a parent directory; run this in the project or in a run")
    here = origin_of(store)
    root = Path(here[0]["project"]) if here else store
    index = read_index(root)
    if names:
        out = []
        for nm in names:
            p = Path(nm)
            hit = next((r for r in index if r["name"] == nm), None)
            if hit:
                out.append((nm, Path(hit["dir"])))
            elif p.is_dir():
                d = p.resolve()
                out.append((d.name if d != root.resolve() else root.name, d))
            elif nm == root.name:
                out.append((nm, root))
            else:
                known = ", ".join([root.name] + [r["name"] for r in index]) or "none"
                raise RunError(f"no run named {nm!r} (runs of this project: {known})")
        return root, out
    alive = [r for r in index if Path(r["dir"]).is_dir()]
    if not alive:
        raise RunError("this project has no runs yet: make one with `rewindagents fork N --name NAME`")
    newest = origin_of(Path(alive[-1]["dir"]))
    key = _start_key(*newest[:2]) if newest else None
    out = [(root.name, root)]
    for r in alive:
        o = origin_of(Path(r["dir"]))
        if o and _start_key(*o[:2]) == key:
            out.append((r["name"], Path(r["dir"])))
    return root, out


def _text_lines(data: bytes | None) -> list[str] | None:
    if data is None:
        return []
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def _plus_minus(old: bytes | None, new: bytes | None) -> tuple[int, int] | None:
    a, b = _text_lines(old), _text_lines(new)
    if a is None or b is None:
        return None
    plus = minus = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            minus += i2 - i1
            plus += j2 - j1
    return plus, minus


def _run_steps(run_dir: Path, root: Path, origin: dict, forked_at: float, is_source: bool) -> list[dict]:
    """The steps that belong to a run after its start. In a run: every step but the fork itself. In the
    source project: the forked session's steps after the fork step, and other sessions' steps since the fork."""
    lp = run_dir / ".rewindagents" / "log.jsonl"
    if not lp.is_file():
        return []
    recs = log.read(lp)
    out = []
    for sess in dict.fromkeys(r["session"] for r in recs):
        recs_s = [r for r in recs if r["session"] == sess]
        steps = rewind.steps_from(recs_s)
        for s in steps:
            if s["event"] == "fork":
                continue
            if is_source:
                ts = next((r.get("ts", 0) for r in recs_s if r["seq"] == s["seq"]), 0)
                if sess == origin["session"]:
                    if s["step"] <= origin["step"]:
                        continue
                elif ts < forked_at:
                    continue
            out.append(s)
    return out


def compare(cwd: str | Path, names: list[str] | None = None, check: str | None = None,
            check_timeout: float = 600.0) -> dict:
    """Everything `compare` prints, as data (also what `compare --json` writes)."""
    root, runs = resolve_runs(Path(cwd), names)
    origins = {lbl: origin_of(d) for lbl, d in runs}
    forks = [(lbl, o) for lbl, o in origins.items() if o]
    if not forks:
        raise RunError("none of these is a run made by `rewindagents fork`, so there is no starting point to "
                       "compare from")
    key = _start_key(*forks[0][1][:2])
    for lbl, o in forks[1:]:
        if _start_key(*o[:2]) != key:
            a, b = forks[0][1][0], o[0]
            raise RunError(f"{forks[0][0]} and {lbl} start from different points (session {a['session'][:8]} "
                           f"step {a['step']} vs session {b['session'][:8]} step {b['step']}); compare runs "
                           f"forked from the same step")
    origin, start, forked_at = forks[0][1]
    start_sha = {c["path"]: (c.get("sha256") or c.get("content_sha256")) for c in start}
    stores = [d / ".rewindagents" / "objects" for _, d in runs]

    def start_bytes(rel: str) -> bytes | None:
        sha = start_sha.get(rel)
        if sha is None:
            return None
        for objs in stores:
            if (objs / sha).is_file():
                return (objs / sha).read_bytes()
        return None

    out_runs = []
    for lbl, d in runs:
        is_source = origins[lbl] is None
        files = run_files(d) or []
        now = {}
        for rel in files:
            try:
                now[rel] = _sha_file(d / rel)
            except OSError:
                continue
        changes = {}
        for rel in sorted(set(now) | set(start_sha)):
            before, after = start_sha.get(rel), now.get(rel)
            if before == after:
                continue
            kind = "created" if rel not in start_sha else "deleted" if after is None else "changed"
            old_b = start_bytes(rel) if rel in start_sha else None
            new_b = None
            if after is not None and (d / rel).stat().st_size <= MAX_CHECKPOINT_BYTES:
                new_b = (d / rel).read_bytes()
            known = (rel not in start_sha or old_b is not None) and (after is None or new_b is not None)
            changes[rel] = {"kind": kind, "sha256": after, "lines": _plus_minus(old_b, new_b) if known else None}
        steps = [s for s in _run_steps(d, root, origin, forked_at, is_source) if s["event"] not in
                 ("rewind", "branch", "fork")]       # the agents' own tool calls; rewinds are yours
        run_agents = sorted({s.get("agent") or "claude" for s in steps})
        plus = sum(c["lines"][0] for c in changes.values() if c["lines"])
        minus = sum(c["lines"][1] for c in changes.values() if c["lines"])
        out_runs.append({"name": lbl, "dir": str(d), "source": is_source, "agents": run_agents,
                         "steps": len(steps), "files": changes, "plus": plus, "minus": minus,
                         "lines_unknown": sum(1 for c in changes.values() if c["lines"] is None)})
    if check:
        for r in out_runs:
            r["check"] = run_check(Path(r["dir"]), check, check_timeout)
    # per file: which runs ended with the same bytes (A, B, ...)
    matrix = {}
    for rel in sorted({f for r in out_runs for f in r["files"]}):
        groups: dict[Any, str] = {}
        row = {}
        for r in out_runs:
            c = r["files"].get(rel)
            if c is None:
                row[r["name"]] = {"kind": "unchanged", "group": None}
                continue
            if c["kind"] == "deleted":
                row[r["name"]] = {"kind": "deleted", "group": None}
                continue
            g = groups.setdefault(c["sha256"], "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[len(groups) % 26])
            row[r["name"]] = {"kind": c["kind"], "group": g}
        matrix[rel] = row
    return {"project": str(root), "session": origin["session"], "step": origin["step"],
            "start_files": len(start), "runs": out_runs, "matrix": matrix, "check": check}


def run_check(d: Path, cmd: str, timeout: float) -> dict:
    """Run the user's command in a run's directory. Its exit code is the result; the last lines are kept."""
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, cwd=d, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        code, text = p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        code, text = None, f"timed out after {timeout:g} s"
    tail = [ln for ln in text.strip().splitlines() if ln.strip()][-CHECK_TAIL:]
    return {"exit": code, "seconds": round(time.monotonic() - t0, 2), "tail": tail}


def lines(c: dict) -> list[str]:
    """The comparison as the terminal shows it."""
    runs = c["runs"]
    root = Path(c["project"])
    out = [f"runs from session {c['session'][:8]} step {c['step']} of {root.name} "
           f"({c['start_files']} files at the start)", ""]
    w = max(8, *(len(r["name"]) for r in runs))
    head = f"  {'run':<{w}}  {'agents':<14} {'steps':>5}  {'files':>5}  {'lines':<20}"
    if c["check"]:
        head += "  check"
    out.append(head.rstrip())
    for r in runs:
        lns = f"+{r['plus']} -{r['minus']}" + (f" (+{r['lines_unknown']} binary)" if r["lines_unknown"] else "")
        ag = ",".join(r["agents"]) or ("-" if r["steps"] == 0 else "?")
        row = f"  {r['name']:<{w}}  {ag:<14} {r['steps']:>5}  {len(r['files']):>5}  {lns:<20}"
        if c["check"]:
            ck = r["check"]
            row += "  " + ("pass" if ck["exit"] == 0 else "timed out" if ck["exit"] is None
                           else f"FAIL (exit {ck['exit']})")
        out.append(row.rstrip())
    if c["matrix"]:
        fw = max(4, *(len(f) for f in c["matrix"]))
        out += ["", (f"  {'file':<{fw}}  " + "  ".join(f"{r['name']:<{max(11, len(r['name']))}}" for r in runs)).rstrip()]
        for rel, row in c["matrix"].items():
            cells = []
            for r in runs:
                cell = row[r["name"]]
                text = "-" if cell["kind"] == "unchanged" else cell["kind"] + (f" {cell['group']}" if cell["group"] else "")
                cells.append(f"{text:<{max(11, len(r['name']))}}")
            out.append((f"  {rel:<{fw}}  " + "  ".join(cells)).rstrip())
        out.append("")
        out.append("  - = as at the start; the same letter in a row = the same bytes in those runs.")
    else:
        out += ["", "  no run has changed a file since the start yet."]
    if c["check"]:
        failed = [r for r in runs if r["check"]["exit"] != 0]
        for r in failed:
            for t in r["check"]["tail"]:
                out.append(f"  {r['name']}: {t}")
    if len(runs) >= 2:
        out.append(f"  how two runs differ: rewindagents compare --diff {runs[0]['name']} {runs[1]['name']}")
    return out


def diff_runs(cwd: str | Path, a: str, b: str) -> list[str]:
    """Unified diffs from run a to run b, for every file either changed since the start and they differ on."""
    from .diff import file_diff
    c = compare(cwd, [a, b])
    ra, rb = c["runs"]
    out = [f"# a/ = run {ra['name']} ({ra['dir']}), b/ = run {rb['name']} ({rb['dir']})\n"]
    for rel in c["matrix"]:
        fa, fb = Path(ra["dir"]) / rel, Path(rb["dir"]) / rel
        da = fa.read_bytes() if fa.is_file() else None
        db = fb.read_bytes() if fb.is_file() else None
        if da != db:
            out.append(file_diff(rel, da, db))
    return out
