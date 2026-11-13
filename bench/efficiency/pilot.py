"""Efficiency pilot: real Claude Code runs (`claude -p`) on the `cart` task, scored by hidden tests.

Plan and rules: bench/EFFICIENCY_PLAN.md. Every agent run is appended to bench/efficiency/runs.jsonl as it
finishes, so a crash loses nothing and a run is never repeated to replace a bad one.

    python3 bench/efficiency/pilot.py solo            # one attempt, one fresh copy
    python3 bench/efficiency/pilot.py race --k 3      # K attempts at once, first to pass the visible check wins
    python3 bench/efficiency/pilot.py h1              # part 1 recorded, a scripted wreck, then resume vs restart
    python3 bench/efficiency/pilot.py report          # the table from runs.jsonl (no agent runs)

Each agent run costs Claude usage. The script refuses to start more agent runs than --budget (default: what
the plan's pilot has left, 9 minus the runs already in runs.jsonl).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
TASK = HERE / "tasks" / "cart"
RUNS = HERE / "runs.jsonl"
PILOT_RUNS = 9
PROMPTS = json.loads((TASK / "prompts.json").read_text(encoding="utf-8"))
VISIBLE = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]


def task_sha() -> str:
    h = hashlib.sha256()
    for p in sorted(TASK.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(TASK).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:16]


def commit() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def runs_so_far() -> list[dict]:
    if not RUNS.exists():
        return []
    return [json.loads(x) for x in RUNS.read_text(encoding="utf-8").splitlines() if x.strip()]


def fresh_copy(parent: Path, name: str) -> Path:
    d = parent / name
    shutil.copytree(TASK / "repo", d)
    g = ["git", "-C", str(d), "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(g + ["add", "-A"], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "task"], check=True)
    return d


def claude_cmd(prompt: str) -> list[str]:
    return ["claude", "-p", prompt, "--output-format", "json", "--setting-sources", "project",
            "--strict-mcp-config", "--no-session-persistence", "--permission-mode", "acceptEdits",
            "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep", "Bash(python3 -m unittest:*)",
            "--max-turns", "30"]


def start(prompt: str, cwd: Path) -> tuple[subprocess.Popen, float]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    return (subprocess.Popen(claude_cmd(prompt), cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True), time.perf_counter())


def visible_ok(d: Path) -> bool:
    return subprocess.run(VISIBLE, cwd=d, capture_output=True, timeout=120).returncode == 0


def hidden_ok(d: Path, files: list[str]) -> bool:
    with tempfile.TemporaryDirectory() as h:
        for f in files:
            shutil.copy(TASK / "hidden" / f, h)
        env = dict(os.environ, PYTHONPATH=str(d))
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", h], cwd=h, env=env,
                           capture_output=True, timeout=120)
        return r.returncode == 0


def finish(p: subprocess.Popen, t0: float, rec: dict, d: Path, hidden: list[str]) -> dict:
    out, err = p.communicate(timeout=1800)
    wall = time.perf_counter() - t0
    try:
        j = json.loads(out)
    except ValueError:
        j = {"parse_error": (out or "")[-400:], "stderr": (err or "")[-400:]}
    u = j.get("usage") or {}
    rec.update({
        "exit": p.returncode, "wall_s": round(wall, 1),
        "duration_ms": j.get("duration_ms"), "num_turns": j.get("num_turns"),
        "cost_usd": j.get("total_cost_usd"), "is_error": j.get("is_error"), "subtype": j.get("subtype"),
        "tokens": {k: u.get(k) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                         "cache_read_input_tokens")},
        "model": next(iter(j.get("modelUsage") or {}), None),
        "visible_pass": visible_ok(d), "hidden_pass": hidden_ok(d, hidden),
    })
    if "parse_error" in j:
        rec["error"] = j
    return rec


def base(workflow: str, prompt_key: str) -> dict:
    return {"task": "cart", "task_sha": task_sha(), "commit": commit(), "workflow": workflow, "prompt": prompt_key,
            "date": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "load_1m": round(os.getloadavg()[0], 1), "claude": subprocess.run(
                ["claude", "--version"], capture_output=True, text=True).stdout.strip()}


def log(rec: dict) -> None:
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec), flush=True)


def budget_ok(n: int, budget: int | None) -> None:
    left = PILOT_RUNS - len(runs_so_far()) if budget is None else budget
    if n > left:
        raise SystemExit("refusing: %d agent runs asked, %d left in the approved pilot" % (n, left))


def solo(tmp: Path) -> None:
    d = fresh_copy(tmp, "solo")
    p, t0 = start(PROMPTS["fix"], d)
    log(finish(p, t0, base("solo", "fix"), d, ["test_hidden_cart.py"]))


def race(tmp: Path, k: int) -> None:
    race_id = datetime.datetime.now().strftime("race-%H%M%S")
    dirs = [fresh_copy(tmp, "r%d" % i) for i in range(k)]
    t0 = time.perf_counter()
    procs = [start(PROMPTS["fix"], d) for d in dirs]
    pending = set(range(k))
    first_pass_s = None
    while pending:
        for i in sorted(pending):
            p, ts = procs[i]
            if p.poll() is None:
                continue
            pending.discard(i)
            rec = finish(p, ts, base("race", "fix"), dirs[i], ["test_hidden_cart.py"])
            rec.update({"race": race_id, "k": k, "attempt": i, "done_after_race_start_s": round(time.perf_counter() - t0, 1)})
            if rec["visible_pass"] and first_pass_s is None:
                first_pass_s = rec["done_after_race_start_s"]
                rec["race_winner"] = True
            log(rec)
        time.sleep(0.5)
    print(json.dumps({"race": race_id, "time_to_first_visible_pass_s": first_pass_s}))


def h1(tmp: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    ra = [sys.executable, "-m", "rewindagents"]
    hidden = ["test_hidden_cart.py", "test_hidden_coupons.py"]
    # setup: part 1 recorded through the real hook (project settings carry it: --setting-sources project)
    d = fresh_copy(tmp, "h1")
    subprocess.run(ra + ["install"], cwd=d, env=env, check=True, capture_output=True)
    p, t0 = start(PROMPTS["fix"], d)
    log(finish(p, t0, base("h1-setup-part1", "fix"), d, ["test_hidden_cart.py"]))
    # the wreck: a shell command recorded as one more agent step, through the hook
    pay = {"session_id": "wreck", "cwd": str(d), "tool_name": "Bash", "tool_use_id": "toolu_wreck",
           "tool_input": {"command": "rm -rf tests cart.py"}}
    hk = ra + ["hook"]
    subprocess.run(hk, input=json.dumps(dict(pay, hook_event_name="PreToolUse")), cwd=d, env=env, text=True, check=True)
    shutil.rmtree(d / "tests")
    (d / "cart.py").unlink()
    subprocess.run(hk, input=json.dumps(dict(pay, hook_event_name="PostToolUse", tool_response={"stdout": ""})),
                   cwd=d, env=env, text=True, check=True)
    # resume: rewind the wreck, then only the remaining work
    t = time.perf_counter()
    rw = subprocess.run(ra + ["rewind", "0", "--session", "wreck"], cwd=d, env=env, capture_output=True, text=True)
    rewind_s = time.perf_counter() - t
    restored = (d / "cart.py").exists() and visible_ok(d)
    p, t0 = start(PROMPTS["coupons"], d)
    rec = finish(p, t0, base("h1-resume", "coupons"), d, hidden)
    rec.update({"rewind_s": round(rewind_s, 3), "rewind_exit": rw.returncode, "restored_part1": restored})
    log(rec)
    # restart: a fresh copy, the whole job again
    d2 = fresh_copy(tmp, "h1-restart")
    p, t0 = start(PROMPTS["both"], d2)
    log(finish(p, t0, base("h1-restart", "both"), d2, hidden))


def med(xs, nd=1):
    xs = [x for x in xs if x is not None]
    return (round(statistics.median(xs), nd), len(xs)) if xs else (None, 0)


def report() -> None:
    rs = runs_so_far()
    print("Medians over the n runs of each workflow; wall-clock by this script's clock, turns and cost as "
          "Claude Code reported them (cost at API list price; the runs used the logged-in account).\n")
    print("| workflow | n | hidden pass | visible pass | median wall s | median turns | median cost USD |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for w in ("solo", "race", "h1-setup-part1", "h1-resume", "h1-restart"):
        xs = [r for r in rs if r["workflow"] == w]
        if not xs:
            continue
        print("| %s | %d | %d/%d | %d/%d | %s | %s | %s |" % (
            w, len(xs), sum(r["hidden_pass"] for r in xs), len(xs), sum(r["visible_pass"] for r in xs), len(xs),
            med([r["wall_s"] for r in xs])[0], med([r["num_turns"] for r in xs])[0],
            med([r["cost_usd"] for r in xs], 3)[0]))
    for rid in sorted({r["race"] for r in rs if r.get("race")}):
        xs = [r for r in rs if r.get("race") == rid]
        win = [r["done_after_race_start_s"] for r in xs if r.get("race_winner")]
        print("%s: K=%d, first visible pass after %s s; attempts finished after %s s" % (
            rid, len(xs), win[0] if win else None, sorted(r["done_after_race_start_s"] for r in xs)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["solo", "race", "h1", "report"])
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--budget", type=int)
    a = ap.parse_args(argv)
    if a.what == "report":
        report()
        return 0
    budget_ok({"solo": 1, "race": a.k, "h1": 3}[a.what], a.budget)
    tmp = Path(tempfile.mkdtemp(prefix="eff-")).resolve()
    try:
        {"solo": lambda: solo(tmp), "race": lambda: race(tmp, a.k), "h1": lambda: h1(tmp)}[a.what]()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
