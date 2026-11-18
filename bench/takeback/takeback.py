"""takeback-bench: can an undo tool take back what a coding agent did, byte for byte?

Each scenario is a small project, a scripted agent session (Write/Edit calls, real shell commands, and
sometimes an edit by hand that no tool sees), and an undo goal. Every tool under test watches the same session
the way it would in real use, then runs its own undo recipe. The bench then compares every file of the project
(and of a directory next to it) with the state the goal asks for:

- exact      every file holds the expected bytes, executable bit and symlink target (SHA-256 compared);
- missed     files the goal says should change back and did not;
- destroyed  files the goal says to leave alone that the undo changed (later work lost);
- ms         wall-clock of the undo command alone; record_ms is what the tool added while the session ran.

Goals:
- ("to", K):   files as they were right after agent step K; changes after it made by hand are kept;
- ("only", K): undo agent step K alone and keep everything after it (a path changed both by step K and after
               it needs the merged bytes, `merge`).

The expected state is not written by hand: the harness snapshots the files after every step of the run, so
the oracle comes from the session itself. A path changed after K both by the agent and by hand needs the
merged bytes, which the scenario states (`merge`).

Tools (measured): rewindagents, through `python -m rewindagents hook` per event exactly as an agent runs it,
then its CLI (`rewind`, and in a second column the same recording undone with `revert` only); git with a commit after every agent step; git with a stash snapshot before the session. Their
recipes are fixed per tool and goal (RECIPES below), not chosen per scenario.

    python3 bench/takeback/takeback.py                       # all tools, all scenarios, table on stdout
    python3 bench/takeback/takeback.py --write               # also writes bench/takeback/results.json
    python3 bench/takeback/takeback.py --scenario S06 --tool rewindagents -v

Stdlib only, no network, no API keys. Each scenario runs in its own temporary directory, deleted after.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
RESULTS = Path(__file__).resolve().parent / "results.json"
BASELINE = Path(__file__).resolve().parent / "results-baseline.json"
REPORT = ROOT / "bench" / "RESULTS.md"
BIG = 20 * 1024 * 1024 + 4096          # just over rewindagents' 20 MB copy limit (hook.MAX_CHECKPOINT_BYTES)
GIT_ID = ["-c", "user.name=bench", "-c", "user.email=bench@localhost", "-c", "commit.gpgsign=false",
          "-c", "core.fileMode=true", "-c", "core.symlinks=true"]


# ---------------------------------------------------------------- scenario model

@dataclass
class Step:
    tool: str                    # Write, Edit, Bash (agent tool calls) or hand (a person, no tool sees it)
    path: str = ""               # Write/Edit/hand: file relative to the project
    text: str = ""               # Write/hand: new content; Edit: replaces `old`
    old: str = ""
    command: str = ""            # Bash: run with sh -c in the project

    @property
    def agent(self) -> bool:
        return self.tool != "hand"


@dataclass
class Scenario:
    id: str
    title: str
    steps: list[Step]
    goal: tuple[str, int]        # ("to", K) or ("only", K); K counts agent steps, 1-based
    git: bool = True             # project is a git repository
    setup: Callable[[Path, Path], None] | None = None   # extra files after the base project
    merge: dict[str, str] = field(default_factory=dict)  # expected bytes where agent and hand both changed a path
    precious: dict[str, str] = field(default_factory=dict)  # path -> text a hand edit added that must survive


APP = "def total(items):\n    return sum(i.price for i in items)\n"
CONFIG = "debug: false\nport: 8080\nretries: 3\n"
TEST_APP = "from app import total\n\n\ndef test_total():\n    assert total([]) == 0\n"
TEST_UTIL = "def test_util():\n    assert True\n"
RUN_SH = "#!/bin/sh\nexec python3 app.py \"$@\"\n"
ENV = "DATABASE_URL=postgres://localhost/dev\nAPI_KEY=local-dev-key\n"
NOTES = "shared notes outside the project\n"


def png_bytes() -> bytes:
    """4 KB of deterministic non-UTF-8 bytes with a PNG signature."""
    out, x = bytearray(b"\x89PNG\r\n\x1a\n"), 12345
    while len(out) < 4096:
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append(x & 0xFF)
    return bytes(out)


def base_project(root: Path, outside: Path, git: bool, extra: Callable | None) -> None:
    files = {"app.py": APP, "config.yaml": CONFIG, "tests/test_app.py": TEST_APP, "tests/test_util.py": TEST_UTIL,
             "README.md": "# shop\n", "scripts/run.sh": RUN_SH, ".gitignore": ".env\n*.log\nbuild/\n", ".env": ENV}
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (root / "scripts/run.sh").chmod(0o755)
    (root / "logo.png").write_bytes(png_bytes())
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "notes.txt").write_text(NOTES, encoding="utf-8")
    if extra:
        extra(root, outside)
    if git:
        g = ["git", "-C", str(root)] + GIT_ID
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-q", "-m", "start"], check=True)


def _big(root: Path, outside: Path) -> None:
    (root / "data").mkdir()
    with open(root / "data" / "fixtures.bin", "wb") as f:
        chunk = bytes(range(256)) * 4096          # 1 MiB
        for _ in range(BIG // len(chunk)):
            f.write(chunk)
        f.write(chunk[: BIG % len(chunk)])


def _symlink(root: Path, outside: Path) -> None:
    os.symlink("config.yaml", root / "config.local.yaml")


EDIT_APP = Step("Edit", "app.py", "    return sum(i.price * i.qty for i in items)\n",
                "    return sum(i.price for i in items)\n")

SCENARIOS: list[Scenario] = [
    Scenario("S01", "Bash `rm -rf tests` deletes the test suite",
             [EDIT_APP, Step("Bash", command="rm -rf tests")], ("to", 1)),
    Scenario("S02", "Bash `sed -i` rewrites config.yaml",
             [EDIT_APP, Step("Bash", command="sed -i.bak 's/debug: false/debug: true/; s/8080/80/' config.yaml"
                                              " && rm config.yaml.bak")], ("to", 1)),
    Scenario("S03", "Write tool overwrites app.py with a stub",
             [Step("Write", "README.md", "# shop\n\nRun scripts/run.sh\n"),
              Step("Write", "app.py", "# TODO\n")], ("to", 1)),
    Scenario("S04", "agent creates helper.py (never committed), then breaks it",
             [Step("Write", "helper.py", "def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n"),
              Step("Edit", "helper.py", "    return x\n", "    return max(lo, min(x, hi))\n")], ("to", 1)),
    Scenario("S05", "Bash overwrites a binary file (logo.png)",
             [EDIT_APP, Step("Bash", command="printf 'not an image' > logo.png")], ("to", 1)),
    Scenario("S06", "Bash `rm .env` deletes a git-ignored file",
             [EDIT_APP, Step("Bash", command="rm .env")], ("to", 1)),
    Scenario("S07", "Bash truncates a tracked file over 20 MB",
             [EDIT_APP, Step("Bash", command=": > data/fixtures.bin")], ("to", 1), setup=_big),
    Scenario("S08", "Bash appends to a file outside the project (../outside/notes.txt)",
             [EDIT_APP, Step("Bash", command="echo 'agent was here' >> ../outside/notes.txt")], ("to", 1)),
    Scenario("S09", "bad Edit to config.yaml, then the user edits the same file by hand",
             [EDIT_APP, Step("Edit", "config.yaml", "debug: true\n", "debug: false\n"),
              Step("hand", "config.yaml", "debug: true\nport: 8080\nretries: 3\n# keep: staging uses 8081\n")],
             ("to", 1), merge={"config.yaml": CONFIG + "# keep: staging uses 8081\n"},
             precious={"config.yaml": "# keep: staging uses 8081"}),
    Scenario("S10", "undo only the bad step (`rm -rf tests`), keep the agent's later work",
             [EDIT_APP, Step("Bash", command="rm -rf tests"),
              Step("Write", "CHANGELOG.md", "## 0.2\n- qty in totals\n")], ("only", 2)),
    Scenario("S11", "Bash `rm -rf scripts` deletes an executable script",
             [EDIT_APP, Step("Bash", command="rm -rf scripts")], ("to", 1)),
    Scenario("S12", "Bash `rm` deletes a symlink in the project",
             [EDIT_APP, Step("Bash", command="rm config.local.yaml")], ("to", 1), setup=_symlink),
    Scenario("S13", "project is not a git repository; Bash `rm -rf tests`",
             [EDIT_APP, Step("Bash", command="rm -rf tests")], ("to", 1), git=False),
    Scenario("S14", "five-step session (Write, Edit, mv, sed -i, new file), back to step 2",
             [Step("Write", "pricing.py", "TAX = 0.08\n"), EDIT_APP,
              Step("Bash", command="mkdir -p docs && mv README.md docs/README.md"),
              Step("Bash", command="sed -i.bak 's/price/cost/g' app.py && rm app.py.bak"),
              Step("Write", "notes.txt", "scratch\n")], ("to", 2)),
    Scenario("S15", "undo the whole session over uncommitted work from before it",
             [Step("Edit", "app.py", "def total(items, tax=0):\n", "def total(items):\n"),
              Step("Bash", command="rm README.md")], ("to", 0)),
    # S09 and S10 where the later work is in the same file as the step taken back
    Scenario("S16", "undo only the bad Edit to config.yaml; the user then edited another line of it by hand",
             [Step("Edit", "config.yaml", "debug: true\n", "debug: false\n"),
              Step("Write", "CHANGELOG.md", "## 0.2\n- debug on\n"),
              Step("hand", "config.yaml", "debug: true\nport: 8080\nretries: 5\n")],
             ("only", 1), merge={"config.yaml": "debug: false\nport: 8080\nretries: 5\n"},
             precious={"config.yaml": "retries: 5"}),
    Scenario("S17", "undo only the bad `sed -i` on config.yaml; a later agent Edit changed another line of it",
             [Step("Bash", command="sed -i.bak 's/debug: false/debug: true/' config.yaml && rm config.yaml.bak"),
              Step("Edit", "config.yaml", "retries: 5\n", "retries: 3\n")],
             ("only", 1), merge={"config.yaml": "debug: false\nport: 8080\nretries: 5\n"},
             precious={"config.yaml": "retries: 5"}),
]
# uncommitted work the user had before the agent started (written after the base commit)
DIRTY = {"S15": ("app.py", APP + "\n\ndef count(items):\n    return len(items)\n")}


# ---------------------------------------------------------------- state and the oracle

def state(root: Path, outside: Path) -> dict[str, Any]:
    """Every file under the project (minus .git and .rewindagents) and under `outside`, as
    "sha256:<hex>[ +x]" or "link:<target>"."""
    out: dict[str, Any] = {}
    for base, prefix in ((root, ""), (outside, "../outside/")):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in (".git", ".rewindagents")]
            for name in dirnames + filenames:
                p = Path(dirpath) / name
                rel = prefix + p.relative_to(base).as_posix()
                if p.is_symlink():
                    out[rel] = "link:" + os.readlink(p)
                elif name in filenames and p.is_file():
                    h = hashlib.sha256()
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            h.update(chunk)
                    x = " +x" if p.stat().st_mode & stat.S_IXUSR else ""
                    out[rel] = "sha256:" + h.hexdigest() + x
    return out


def text_state(text: str, executable: bool = False) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest() + (" +x" if executable else "")


def expected(scn: Scenario, snaps: list[dict], agent_index: list[int]) -> dict[str, Any]:
    """The state the goal asks for. snaps[i] is the state after scenario step i (snaps[0]: before the session);
    agent_index[k] is the scenario step index of agent step k (agent_index[0] = 0)."""
    kind, k = scn.goal
    final = snaps[-1]
    paths = set().union(*snaps)
    out: dict[str, Any] = {}
    if kind == "to":
        at = snaps[agent_index[k]]
        for p in paths:
            agent_changed = hand_changed = False
            for i in range(agent_index[k] + 1, len(snaps)):
                if snaps[i].get(p) != snaps[i - 1].get(p):
                    if scn.steps[i - 1].agent:
                        agent_changed = True
                    else:
                        hand_changed = True
            if agent_changed and hand_changed:
                if p not in scn.merge:
                    raise ValueError(f"{scn.id}: {p} changed by the agent and by hand after step {k}: give merge")
                out[p] = text_state(scn.merge[p])
            elif agent_changed:
                v = at.get(p)
                if v is not None:
                    out[p] = v
            else:
                v = final.get(p)
                if v is not None:
                    out[p] = v
    else:   # only: undo agent step k, keep the rest
        i = agent_index[k]
        for p in paths:
            later = any(snaps[j].get(p) != snaps[j - 1].get(p) for j in range(i + 1, len(snaps)))
            if snaps[i].get(p) != snaps[i - 1].get(p) and later:
                if p not in scn.merge:
                    raise ValueError(f"{scn.id}: {p} changed by step {k} and after it: give merge")
                out[p] = text_state(scn.merge[p])
                continue
            v = snaps[i - 1].get(p) if snaps[i].get(p) != snaps[i - 1].get(p) else final.get(p)
            if v is not None:
                out[p] = v
    return out


def judge(want: dict, pre: dict, post: dict, scn: Scenario, root: Path) -> dict:
    paths = sorted(set(want) | set(pre) | set(post))
    missed = [p for p in paths if want.get(p) != pre.get(p) and post.get(p) != want.get(p)]
    destroyed = [p for p in paths if want.get(p) == pre.get(p) and post.get(p) != pre.get(p)]
    for p, marker in scn.precious.items():
        try:
            kept = marker in (root / p).read_text(encoding="utf-8")
        except OSError:
            kept = False
        if not kept and p not in destroyed:
            destroyed.append(p)
    wrong = [p for p in paths if post.get(p) != want.get(p)]
    # bytes right, executable bit wrong
    mode_only = [p for p in wrong if post.get(p) and want.get(p)
                 and post[p].replace(" +x", "") == want[p].replace(" +x", "")]
    return {"exact": not wrong, "missed": missed, "destroyed": sorted(destroyed),
            "wrong": wrong, "mode_only": mode_only, "untouched": post == pre}


# ---------------------------------------------------------------- tools

def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


class Tool:
    name = ""
    measured = True

    def applies(self, scn: Scenario) -> str | None:
        """None when the tool can run this scenario, else why not."""
        return None

    def start(self, root: Path) -> None: ...
    def before(self, n: int, step: Step, root: Path) -> None: ...
    def after(self, n: int, step: Step, root: Path) -> None: ...
    def undo(self, scn: Scenario, root: Path) -> tuple[int, str]: ...


class RewindAgents(Tool):
    """The real hook process per event (PreToolUse, PostToolUse), Claude Code's payload; undo through the CLI."""
    name = "rewindagents"

    def __init__(self):
        self.env = dict(os.environ, PYTHONPATH=str(SRC))
        self.env.pop("CLAUDE_PROJECT_DIR", None)

    def _payload(self, n: int, step: Step, root: Path, event: str) -> dict:
        if step.tool == "Bash":
            inp: dict = {"command": step.command}
        elif step.tool == "Write":
            inp = {"file_path": str(root / step.path), "content": step.text}
        else:
            inp = {"file_path": str(root / step.path), "old_string": step.old, "new_string": step.text}
        p = {"session_id": "bench", "cwd": str(root), "hook_event_name": event, "tool_name": step.tool,
             "tool_input": inp, "tool_use_id": "toolu_%03d" % n, "transcript_path": ""}
        if event == "PostToolUse":
            p["tool_response"] = {"stdout": "", "stderr": ""} if step.tool == "Bash" else {"filePath": inp["file_path"]}
        return p

    def _hook(self, payload: dict, root: Path) -> None:
        p = subprocess.run([sys.executable, "-m", "rewindagents", "hook"], input=json.dumps(payload), cwd=root,
                           env=self.env, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("hook failed: %r" % (p,))

    def before(self, n, step, root):
        self._hook(self._payload(n, step, root, "PreToolUse"), root)

    def after(self, n, step, root):
        self._hook(self._payload(n, step, root, "PostToolUse"), root)

    def cli(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        return run([sys.executable, "-m", "rewindagents", *args], root, self.env)

    def undo(self, scn, root):
        kind, k = scn.goal
        if kind == "to":
            p = self.cli(root, "rewind", str(k))
        else:
            # no single-step revert command: rewind to k-1 for the files step k changed (what `replay --step k`
            # names), leaving every other file as it is
            sys.path.insert(0, str(SRC))
            from rewindagents import rewind as rw   # noqa: E402  (reads the log as `replay` does)
            step = rw.steps(root / ".rewindagents" / "log.jsonl")[k - 1]
            only = sorted({cp["path"] for cp in step["checkpoints"]})
            args = ["rewind", str(k - 1)]
            for o in only:
                args += ["--only", o]
            p = self.cli(root, *args)
        return p.returncode, (p.stdout + p.stderr).strip()


class RewindAgentsRevert(RewindAgents):
    """The same recording; undo with `revert` only, one command per agent step taken back, newest first.
    Goal ("only", K): `revert K`. Goal ("to", K): `revert` every agent step after K, from the last one down.
    Step numbers stay valid because each revert is appended after them. Stops at the first non-zero exit."""
    name = "rewindagents revert"

    def undo(self, scn, root):
        kind, k = scn.goal
        last = sum(1 for s in scn.steps if s.agent)
        todo = [k] if kind == "only" else list(range(last, k, -1))
        out = []
        for n in todo:
            p = self.cli(root, "revert", str(n))
            out.append((p.stdout + p.stderr).strip())
            if p.returncode != 0:
                return p.returncode, "\n".join(out)
        return 0, "\n".join(out)


class GitPerStep(Tool):
    """Like aider's auto-commits, applied to every agent step including shell commands (more than aider does):
    `git add -A && git commit` before the session (uncommitted work) and after each agent step.
    Undo to step K: `git reset --hard <commit K> && git clean -fd`. Undo only step K: `git revert <commit K>`."""
    name = "git commit per step"

    def applies(self, scn):
        return None if scn.git else "needs a git repository"

    def _commit(self, root: Path, msg: str) -> str:
        g = ["git", "-C", str(root)] + GIT_ID
        subprocess.run(g + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", msg], check=True, capture_output=True)
        return run(["git", "rev-parse", "HEAD"], root).stdout.strip()

    def start(self, root):
        self.commits = [self._commit(root, "before the session")]

    def after(self, n, step, root):
        if step.agent:
            self.commits.append(self._commit(root, "step %d" % n))

    def undo(self, scn, root):
        kind, k = scn.goal
        g = ["git"] + GIT_ID
        if kind == "to":
            a = run(g + ["reset", "-q", "--hard", self.commits[k]], root)
            b = run(g + ["clean", "-q", "-fd"], root)
            return a.returncode or b.returncode, (a.stderr + b.stderr).strip()
        p = run(g + ["revert", "--no-edit", self.commits[k]], root)
        return p.returncode, (p.stdout + p.stderr).strip()


class GitStash(Tool):
    """A snapshot before the agent starts, the advice for agents with no undo of their own:
    `git stash push --include-untracked` then `git stash apply` (files unchanged, snapshot kept).
    Undo (any goal): `git reset --hard && git clean -fd && git stash apply`, i.e. back to the session start."""
    name = "git stash snapshot"

    def applies(self, scn):
        return None if scn.git else "needs a git repository"

    def start(self, root):
        g = ["git"] + GIT_ID
        before = run(["git", "stash", "list"], root).stdout
        run(g + ["stash", "push", "-q", "--include-untracked", "-m", "before agent"], root)
        self.stashed = run(["git", "stash", "list"], root).stdout != before
        if self.stashed:
            run(g + ["stash", "apply", "-q"], root)

    def undo(self, scn, root):
        g = ["git"] + GIT_ID
        ps = [run(g + ["reset", "-q", "--hard"], root), run(g + ["clean", "-q", "-fd"], root)]
        if self.stashed:
            ps.append(run(g + ["stash", "apply", "-q"], root))
        return max(p.returncode for p in ps), "".join(p.stderr for p in ps).strip()


TOOLS: dict[str, type[Tool]] = {t.name: t for t in (RewindAgents, RewindAgentsRevert, GitPerStep, GitStash)}


# ---------------------------------------------------------------- one run

def apply_step(step: Step, root: Path) -> None:
    p = root / step.path
    if step.tool == "Bash":
        r = subprocess.run(["sh", "-c", step.command], cwd=root, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("scenario command failed: %s: %s" % (step.command, r.stderr))
    elif step.tool == "Edit":
        text = p.read_text(encoding="utf-8")
        if step.old not in text:
            raise RuntimeError("Edit: %r not in %s" % (step.old, step.path))
        p.write_text(text.replace(step.old, step.text, 1), encoding="utf-8")
    else:   # Write, hand
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(step.text, encoding="utf-8")


def run_one(scn: Scenario, tool: Tool, verbose: bool = False) -> dict:
    why = tool.applies(scn)
    if why:
        return {"scenario": scn.id, "tool": tool.name, "applies": False, "why": why}
    tmp = Path(tempfile.mkdtemp(prefix="takeback-")).resolve()
    try:
        root, outside = tmp / "project", tmp / "outside"
        root.mkdir()
        base_project(root, outside, scn.git, scn.setup)
        if scn.id in DIRTY:
            rel, text = DIRTY[scn.id]
            (root / rel).write_text(text, encoding="utf-8")
        t = time.perf_counter()
        tool.start(root)
        record_s = time.perf_counter() - t
        snaps, agent_index, n = [state(root, outside)], [0], 0
        for i, step in enumerate(scn.steps, 1):
            if step.agent:
                n += 1
                agent_index.append(i)
            t = time.perf_counter()
            if step.agent:
                tool.before(n, step, root)
            record_s += time.perf_counter() - t
            apply_step(step, root)
            t = time.perf_counter()
            if step.agent:
                tool.after(n, step, root)
            record_s += time.perf_counter() - t
            snaps.append(state(root, outside))
        want = expected(scn, snaps, agent_index)
        pre = snaps[-1]
        t = time.perf_counter()
        code, out = tool.undo(scn, root)
        undo_s = time.perf_counter() - t
        post = state(root, outside)
        res = judge(want, pre, post, scn, root)
        res.update({"scenario": scn.id, "tool": tool.name, "applies": True, "exit": code,
                    "undo_ms": round(undo_s * 1000, 1), "record_ms": round(record_s * 1000, 1),
                    "output": out[-600:]})
        if verbose:
            print(json.dumps(res, indent=1), file=sys.stderr)
        return res
    finally:
        remove_tree(tmp)


def remove_tree(path: Path) -> None:
    """Delete a scenario's temp dir, best effort. On Windows git leaves its object files read-only, and
    rmtree cannot delete a read-only file there: clear the flag and retry (the shutil docs' own recipe)."""
    def writable_then_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=writable_then_retry)
        else:
            shutil.rmtree(path, onerror=writable_then_retry)
    except OSError:
        pass


def outcome(r: dict) -> str:
    if not r["applies"]:
        return "n/a (%s)" % r["why"]
    if r["exact"]:
        return "exact"
    mode = set(r.get("mode_only") or [])
    bits = []
    if r["destroyed"]:
        bits.append("DESTROYED " + ", ".join(r["destroyed"]))
    if r["missed"]:
        bits.append("missed " + ", ".join(p + (" (bytes back, +x lost)" if p in mode else "") for p in r["missed"]))
    if r["untouched"] and r["exit"] != 0:
        bits.insert(0, "refused")
    text = "; ".join(bits) or "wrong: " + ", ".join(r["wrong"])
    # did the user learn something was not put back? exit 0 with a miss is a silent miss
    return text + (" (exit 0: silent)" if r["exit"] == 0 else " (exit %d)" % r["exit"])


# ---------------------------------------------------------------- report

def machine() -> dict:
    m = {"os": platform.system(), "os_release": platform.release(), "arch": platform.machine(),
         "cpus": os.cpu_count(), "python": platform.python_version(),
         "git": run(["git", "--version"], ROOT).stdout.strip()}
    if platform.system() == "Darwin":
        m["os_version"] = "macOS " + platform.mac_ver()[0]
    return m


def commit() -> str | None:
    p = run(["git", "rev-parse", "--short", "HEAD"], ROOT)
    return p.stdout.strip() or None


def bench(scenarios: list[Scenario], tools: list[str], verbose: bool = False) -> dict:
    rows = [run_one(s, TOOLS[t](), verbose) for s in scenarios for t in tools]
    return {"bench": "takeback-bench", "version": 1,
            "date": datetime.datetime.now().astimezone().strftime("%Y-%m-%d"),
            "machine": machine(), "commit": commit(), "tools": tools,
            "scenarios": [{"id": s.id, "title": s.title, "goal": list(s.goal)} for s in scenarios],
            "results": rows}


def summary(r: dict) -> dict[str, dict]:
    out = {}
    for t in r["tools"]:
        rows = [x for x in r["results"] if x["tool"] == t]
        ran = [x for x in rows if x["applies"]]
        out[t] = {"exact": sum(x["exact"] for x in ran), "ran": len(ran), "scenarios": len(rows),
                  "destroyed": sum(bool(x["destroyed"]) for x in ran)}
    return out


def table(r: dict) -> str:
    tools = r["tools"]
    lines = ["| Scenario | " + " | ".join(tools) + " |", "|---|" + "---|" * len(tools)]
    by = {(x["scenario"], x["tool"]): x for x in r["results"]}
    for s in r["scenarios"]:
        cells = [outcome(by[(s["id"], t)]) for t in tools]
        lines.append("| %s %s | %s |" % (s["id"], s["title"], " | ".join(cells)))
    sm = summary(r)
    lines.append("| **exact, of scenarios run** | " + " | ".join(
        "**%d / %d**%s" % (sm[t]["exact"], sm[t]["ran"],
                           "" if sm[t]["ran"] == sm[t]["scenarios"] else " (%d n/a)" % (sm[t]["scenarios"] - sm[t]["ran"]))
        for t in tools) + " |")
    lines.append("| **runs that destroyed later work** | " + " | ".join(str(sm[t]["destroyed"]) for t in tools) + " |")
    return "\n".join(lines)


def timing(r: dict) -> str:
    tools = r["tools"]
    lines = ["| Scenario | " + " | ".join("%s undo / record" % t for t in tools) + " |", "|---|" + "---|" * len(tools)]
    by = {(x["scenario"], x["tool"]): x for x in r["results"]}
    for s in r["scenarios"]:
        cells = []
        for t in tools:
            x = by[(s["id"], t)]
            cells.append("{:,.0f} / {:,.0f} ms".format(x["undo_ms"], x["record_ms"]) if x["applies"] else "n/a")
        lines.append("| %s | %s |" % (s["id"], " | ".join(cells)))
    return "\n".join(lines)


def where(r: dict) -> str:
    m = r["machine"]
    host = m.get("os_version") or "%s %s" % (m["os"], m["os_release"])
    return "%s, %s, %d CPUs, Python %s, %s, on %s at commit %s" % (
        host, m["arch"], m["cpus"], m["python"], m["git"], r["date"], r["commit"])


def block(r: dict) -> str:
    return "\n".join(["Measured on %s." % where(r), "", table(r), "", "Undo time / time the tool added while the "
                      "session ran (one run each, wall-clock):", "", timing(r)])


def write_md(path: Path = REPORT) -> None:
    """Put the rendering of results-baseline.json and results.json between their markers in RESULTS.md."""
    text = path.read_text(encoding="utf-8")
    for tag, src in (("baseline", BASELINE), ("current", RESULTS)):
        a, b = "<!-- takeback:%s:start -->" % tag, "<!-- takeback:%s:end -->" % tag
        i, j = text.index(a) + len(a), text.index(b)
        r = json.loads(src.read_text(encoding="utf-8"))
        text = text[:i] + "\n" + block(r) + "\n" + text[j:]
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="takeback-bench: does the undo put back the exact bytes?")
    ap.add_argument("--scenario", action="append", help="run only this scenario id (repeatable)")
    ap.add_argument("--tool", action="append", choices=sorted(TOOLS), help="run only this tool (repeatable)")
    ap.add_argument("--write", action="store_true", help="write bench/takeback/results.json")
    ap.add_argument("--out", type=Path, help="write the results JSON here")
    ap.add_argument("--markdown", action="store_true",
                    help="only re-render bench/RESULTS.md from the saved results files, no measuring")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.markdown:
        write_md()
        print("wrote %s" % REPORT)
        return 0
    scns = [s for s in SCENARIOS if not a.scenario or s.id in a.scenario]
    if not scns:
        ap.error("no scenario matches %s" % a.scenario)
    tools = a.tool or list(TOOLS)
    r = bench(scns, tools, a.verbose)
    print(table(r))
    print()
    print(timing(r))
    out = a.out or (RESULTS if a.write else None)
    if out:
        out.write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8")
        print("\nwrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
