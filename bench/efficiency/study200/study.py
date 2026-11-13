"""The 200-run efficiency study: real Claude Code runs (`claude -p`) on 10 tasks, scored by hidden tests.

Pre-registration (tasks, workflows, metrics, analysis, stopping rules): bench/EFFICIENCY_STUDY_PLAN.md.
Everything here follows it; nothing is tuned after a run.

    python3 bench/efficiency/study200/study.py run             # run (or resume) the fixed schedule
    python3 bench/efficiency/study200/study.py run --dry-run   # same, with a stub agent that costs nothing
    python3 bench/efficiency/study200/study.py schedule        # print the fixed schedule

Every agent run is appended to bench/efficiency/runs-200.jsonl the moment it is scored, so a crash loses
nothing; a re-start skips units already complete. Analysis: analyze.py (reads the log, runs no agent).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "src"
TASKS_DIR = HERE / "tasks"
RUNS = ROOT / "bench" / "efficiency" / "runs-200.jsonl"
DRY_RUNS = HERE / "dry-runs.jsonl"
TASKS = sorted(p.name for p in TASKS_DIR.iterdir() if p.is_dir())
MODEL = "claude-opus-5-5"
CAP_RUNS = 200
CAP_USD = 40.0
DEFAULT_RUN_COST = 0.25          # projection before any run has reported a cost
K = 3
SOLO_PER_TASK = 5
RACES_PER_TASK = 4
INFRA_WAIT_S = 300
INFRA_GIVE_UP_S = 3600
CHECK = "Run `python3 -m unittest discover -s tests` to check. Do not edit the existing tests."
INFRA_RE = re.compile(r"rate.?limit|usage limit|limit reached|overloaded|api error|\b5\d\d\b|credit balance|"
                      r"temporarily unavailable|connection error|timed out", re.I)


# ---------------------------------------------------------------- the fixed schedule (pre-registered)

def schedule() -> list[dict]:
    """Round 1: per task an H1 unit (solo attempt 0, wreck, resume, restart) and race 0.
    Rounds 2-4: per task solo attempt r and race r. Round 5: per task solo attempt 4. 190 agent runs."""
    units = []
    for t in TASKS:
        units.append({"id": "%s/h1" % t, "kind": "h1", "task": t, "runs": 3})
        units.append({"id": "%s/race0" % t, "kind": "race", "task": t, "n": 0, "runs": K})
    for r in range(1, RACES_PER_TASK):
        for t in TASKS:
            units.append({"id": "%s/solo%d" % (t, r), "kind": "solo", "task": t, "n": r, "runs": 1})
            units.append({"id": "%s/race%d" % (t, r), "kind": "race", "task": t, "n": r, "runs": K})
    for r in range(RACES_PER_TASK, SOLO_PER_TASK):
        for t in TASKS:
            units.append({"id": "%s/solo%d" % (t, r), "kind": "solo", "task": t, "n": r, "runs": 1})
    return units


# ---------------------------------------------------------------- task material

def text(task: str, name: str) -> str:
    return (TASKS_DIR / task / name).read_text(encoding="utf-8").strip()


def prompt(task: str, which: str) -> str:
    issue, part2 = text(task, "issue.md"), text(task, "part2.md")
    if which == "fix":
        return "Resolve this issue in the code in the current directory.\n\n%s\n\n%s" % (issue, CHECK)
    if which == "part2":
        return "%s\n\n%s" % (part2, CHECK)
    if which == "both":
        return ("Two jobs in the code in the current directory. First, resolve this issue:\n\n%s\n\n"
                "Then: %s\n\n%s" % (issue, part2, CHECK))
    raise ValueError(which)


def task_sha(task: str) -> str:
    h = hashlib.sha256()
    base = TASKS_DIR / task
    for p in sorted(base.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(base).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:16]


def module_name(task: str) -> str:
    return next(p.name for p in (TASKS_DIR / task / "repo").glob("*.py"))


def git(d: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(d), "-c", "user.name=bench", "-c", "user.email=bench@localhost",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def fresh_copy(parent: Path, task: str, name: str) -> Path:
    """The task repo as a fresh git repository with the rewindagents hook installed (every arm the same).
    The hook config and its log are hidden from `git status` through .git/info/exclude."""
    d = parent / name
    shutil.copytree(TASKS_DIR / task / "repo", d)
    env = dict(os.environ, PYTHONPATH=str(SRC))
    subprocess.run([sys.executable, "-m", "rewindagents", "install"], cwd=d, env=env, check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    with open(d / ".git" / "info" / "exclude", "a", encoding="utf-8") as f:
        f.write(".claude/\n.rewindagents/\n__pycache__/\n")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "task")
    return d


# ---------------------------------------------------------------- scoring

def run_tests(test_dir: Path, code_dir: Path, files: list[str] | None = None) -> bool:
    with tempfile.TemporaryDirectory() as h:
        if files is None:
            src = test_dir
        else:
            for f in files:
                shutil.copy(test_dir / f, h)
            src = Path(h)
        env = dict(os.environ, PYTHONPATH=str(code_dir), PYTHONDONTWRITEBYTECODE="1")
        try:
            r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(src), "-t", str(src)],
                               cwd=str(code_dir), env=env, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False
        return r.returncode == 0


def visible_ok(d: Path) -> bool:
    """What a user's check sees: the tests in the agent's directory, as the agent left them."""
    if not (d / "tests").is_dir():
        return False
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=d,
                           capture_output=True, timeout=120, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0


def score(d: Path, task: str, part2: bool) -> dict:
    hid = TASKS_DIR / task / "hidden"
    out = {"visible_pass": visible_ok(d),
           "visible_orig_pass": run_tests(TASKS_DIR / task / "repo" / "tests", d),
           "hidden_fix_pass": run_tests(hid, d, ["test_hidden_fix.py"])}
    if part2:
        out["hidden_part2_pass"] = run_tests(hid, d, ["test_hidden_part2.py"])
        out["hidden_pass"] = out["hidden_fix_pass"] and out["hidden_part2_pass"]
    else:
        out["hidden_pass"] = out["hidden_fix_pass"]
    return out


# ---------------------------------------------------------------- agent processes

def claude_cmd(p: str, claude_bin: str) -> list[str]:
    # Same flags as the pilot (bench/efficiency/pilot.py), plus the model pinned to the one the pilot reported.
    return [claude_bin, "-p", p, "--model", MODEL, "--output-format", "json", "--setting-sources", "project",
            "--strict-mcp-config", "--no-session-persistence", "--permission-mode", "acceptEdits",
            "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep", "Bash(python3 -m unittest:*)",
            "--max-turns", "30"]


class Agent:
    def __init__(self, p: str, cwd: Path, claude_bin: str):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        self.t0 = time.perf_counter()
        self.proc = subprocess.Popen(claude_cmd(p, claude_bin), cwd=cwd, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        self.t_exit = None

    def poll(self) -> bool:
        if self.t_exit is None and self.proc.poll() is not None:
            self.t_exit = time.perf_counter()
        return self.t_exit is not None

    def collect(self) -> dict:
        try:
            out, err = self.proc.communicate(timeout=1800)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, err = self.proc.communicate()
        if self.t_exit is None:
            self.t_exit = time.perf_counter()
        try:
            j = json.loads(out)
        except ValueError:
            j = {"parse_error": True}
        u = j.get("usage") or {}
        rec = {"exit": self.proc.returncode, "wall_s": round(self.t_exit - self.t0, 2),
               "duration_ms": j.get("duration_ms"), "num_turns": j.get("num_turns"),
               "cost_usd": j.get("total_cost_usd"), "is_error": j.get("is_error"), "subtype": j.get("subtype"),
               "tokens": {k: u.get(k) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                "cache_read_input_tokens")},
               "model": next(iter(j.get("modelUsage") or {}), None)}
        result_text = str(j.get("result") or "")
        blob = result_text + " " + (err or "")[-2000:] + (" " + (out or "")[-500:] if "parse_error" in j else "")
        # infrastructure, not the agent: no parsable result at all, or an error whose text names a rate/usage
        # limit or an API failure. A run that ends on --max-turns or a wrong fix is the agent's result.
        infra = "parse_error" in j or bool(j.get("is_error") and INFRA_RE.search(blob))
        rec["infra_error"] = bool(infra)
        if infra or j.get("is_error"):
            rec["error_text"] = blob.strip()[-600:]
        return rec


# ---------------------------------------------------------------- log

class Log:
    def __init__(self, path: Path):
        self.path = path

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def write(self, rec: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print("  %-22s %-12s wall %6.1fs  cost %s  visible %s  hidden %s%s" % (
            rec["unit"], rec["workflow"], rec["wall_s"], rec.get("cost_usd"), rec.get("visible_pass"),
            rec.get("hidden_pass"), "  INFRA" if rec.get("infra_error") else ""), flush=True)


def base(unit: dict, workflow: str, which: str, ctx: dict) -> dict:
    return {"unit": unit["id"], "exec": ctx["exec"], "task": unit["task"], "task_sha": task_sha(unit["task"]),
            "workflow": workflow, "prompt": which, "attempt": unit.get("n", 0),
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "load_1m": round(os.getloadavg()[0], 1), "claude": ctx["ver"], "commit": ctx["commit"]}


# ---------------------------------------------------------------- units

def run_solo(unit, tmp, ctx):
    d = fresh_copy(tmp, unit["task"], "solo")
    a = Agent(prompt(unit["task"], "fix"), d, ctx["bin"])
    while not a.poll():
        time.sleep(0.2)
    rec = base(unit, "solo", "fix", ctx)
    rec.update(a.collect())
    rec.update(score(d, unit["task"], part2=False))
    ctx["log"].write(rec)
    return [rec]


def run_race(unit, tmp, ctx):
    t = unit["task"]
    dirs = [fresh_copy(tmp, t, "r%d" % i) for i in range(K)]
    t0 = time.perf_counter()
    agents = [Agent(prompt(t, "fix"), d, ctx["bin"]) for d in dirs]
    while not all(a.poll() for a in agents):
        time.sleep(0.2)
    recs = []
    for i, (a, d) in enumerate(zip(agents, dirs)):
        rec = base(unit, "race", "fix", ctx)
        rec.update(a.collect())
        rec.update(score(d, t, part2=False))
        rec.update({"race": unit["id"], "k": K, "slot": i, "done_after_race_start_s": round(a.t_exit - t0, 2)})
        recs.append(rec)
    passing = sorted((r for r in recs if r["visible_pass"]), key=lambda r: r["done_after_race_start_s"])
    for r in recs:
        r["race_winner"] = bool(passing) and r is passing[0]
        ctx["log"].write(r)
    return recs


def run_h1(unit, tmp, ctx):
    t = unit["task"]
    env = dict(os.environ, PYTHONPATH=str(SRC))
    ra = [sys.executable, "-m", "rewindagents"]
    recs = run_solo(dict(unit, n=0), tmp, ctx)          # solo attempt 0 doubles as H1 part 1
    d = tmp / "solo"
    if recs[0].get("infra_error"):
        return recs
    # the wreck, fixed in advance: the agent's shell deletes the tests and the module, recorded through the hook
    mod = module_name(t)
    before = tree_sha(d)
    pay = {"session_id": "wreck", "cwd": str(d), "tool_name": "Bash", "tool_use_id": "toolu_wreck",
           "tool_input": {"command": "rm -rf tests %s" % mod}}
    hk = ra + ["hook"]
    subprocess.run(hk, input=json.dumps(dict(pay, hook_event_name="PreToolUse")), cwd=d, env=env, text=True,
                   check=True, capture_output=True)
    shutil.rmtree(d / "tests", ignore_errors=True)
    (d / mod).unlink(missing_ok=True)
    subprocess.run(hk, input=json.dumps(dict(pay, hook_event_name="PostToolUse", tool_response={"stdout": ""})),
                   cwd=d, env=env, text=True, check=True, capture_output=True)
    # resume: rewind the wreck, then only part 2
    t1 = time.perf_counter()
    rw = subprocess.run(ra + ["rewind", "0", "--session", "wreck"], cwd=d, env=env, capture_output=True, text=True)
    rewind_s = time.perf_counter() - t1
    restored = tree_sha(d) == before
    a = Agent(prompt(t, "part2"), d, ctx["bin"])
    while not a.poll():
        time.sleep(0.2)
    rec = base(unit, "h1-resume", "part2", ctx)
    rec.update(a.collect())
    rec.update(score(d, t, part2=True))
    rec.update({"rewind_s": round(rewind_s, 3), "rewind_exit": rw.returncode, "restored": restored,
                "part1_hidden_pass": recs[0]["hidden_pass"]})
    ctx["log"].write(rec)
    recs.append(rec)
    # restart: a fresh copy, the whole job from zero
    d2 = fresh_copy(tmp, t, "restart")
    a = Agent(prompt(t, "both"), d2, ctx["bin"])
    while not a.poll():
        time.sleep(0.2)
    rec = base(unit, "h1-restart", "both", ctx)
    rec.update(a.collect())
    rec.update(score(d2, t, part2=True))
    ctx["log"].write(rec)
    recs.append(rec)
    return recs


def tree_sha(d: Path) -> str:
    """SHA-256 over every file the agent works on (not .git, the hook's log or caches)."""
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d)
        if p.is_file() and not {".git", ".rewindagents", "__pycache__", ".claude"} & set(rel.parts):
            h.update(rel.as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


RUNNERS = {"solo": run_solo, "race": run_race, "h1": run_h1}


# ---------------------------------------------------------------- the loop with its stopping rules

def complete_execs(recs: list[dict]) -> dict:
    """unit id -> the first execution of it whose every run finished without an infrastructure error.
    An execution with an infra error, or cut short by a crash, is not complete; its runs stay in the log
    (they count against the caps and are listed by the analysis) and the unit is executed again."""
    units = {u["id"]: u for u in schedule()}
    by = {}
    for r in recs:
        by.setdefault((r["unit"], r["exec"]), []).append(r)
    out = {}
    for (uid, ex), rs in sorted(by.items(), key=lambda kv: kv[1][0]["date"]):
        if uid in out or uid not in units:
            continue
        if len(rs) == units[uid]["runs"] and not any(r.get("infra_error") for r in rs):
            out[uid] = ex
    return out


def run(dry: bool, only: int | None) -> int:
    log = Log(DRY_RUNS if dry else RUNS)
    claude_bin = str(HERE / "stub_agent.py") if dry else "claude"
    ver = "stub" if dry else subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    infra_since = None
    done_units = 0
    while True:
        recs = log.all()
        done = complete_execs(recs)
        todo = [u for u in schedule() if u["id"] not in done]
        if not todo:
            print("schedule complete")
            return 0
        if only is not None and done_units >= only:
            return 0
        unit = todo[0]
        started = len(recs)
        spent = sum(r.get("cost_usd") or 0 for r in recs)
        costs = [r["cost_usd"] for r in recs if r.get("cost_usd")]
        per_run = statistics.median(costs) if costs else DEFAULT_RUN_COST
        if started + unit["runs"] > CAP_RUNS:
            print("STOP: run cap: %d started, unit %s needs %d more (cap %d); results are PARTIAL" % (
                started, unit["id"], unit["runs"], CAP_RUNS))
            return 2
        if spent + per_run * unit["runs"] > CAP_USD:
            print("STOP: cost cap: %.2f USD spent, unit %s projected %.2f more (cap %.2f); results are PARTIAL" % (
                spent, unit["id"], per_run * unit["runs"], CAP_USD))
            return 2
        ctx = {"log": log, "bin": claude_bin, "ver": ver, "commit": commit,
               "exec": "%s@%d" % (unit["id"], int(time.time() * 1000))}
        print("%s  unit %s  (runs so far %d, cost so far %.2f USD)" % (
            datetime.datetime.now().strftime("%H:%M:%S"), unit["id"], started, spent), flush=True)
        tmp = Path(tempfile.mkdtemp(prefix="eff200-")).resolve()
        try:
            out = RUNNERS[unit["kind"]](unit, tmp, ctx)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if any(r.get("infra_error") for r in out):
            infra_since = infra_since or time.time()
            if time.time() - infra_since > INFRA_GIVE_UP_S:
                print("STOP: infrastructure/usage-limit errors for more than an hour; results are PARTIAL")
                return 3
            print("infrastructure error (rate/usage limit or API); waiting %d s, then the unit runs again" %
                  INFRA_WAIT_S, flush=True)
            time.sleep(0 if dry else INFRA_WAIT_S)
            continue
        infra_since = None
        done_units += 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "schedule"])
    ap.add_argument("--dry-run", action="store_true", help="stub agent, log to dry-runs.jsonl, no cost")
    ap.add_argument("--units", type=int, help="stop after this many units (for staged running)")
    a = ap.parse_args(argv)
    if a.what == "schedule":
        units = schedule()
        for u in units:
            print(u["id"], u["runs"])
        print("units %d, agent runs %d" % (len(units), sum(u["runs"] for u in units)))
        return 0
    return run(a.dry_run, a.units)


if __name__ == "__main__":
    sys.exit(main())
