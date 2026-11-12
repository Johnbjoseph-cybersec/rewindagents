"""How long the hook adds to one tool call, measured.

For each project size (default 100, 1,000 and 10,000 files, in a fresh git repository), this runs the hook the
way Claude Code runs it: a new `python -m rewindagents hook` process per event, the JSON payload on stdin. One
tool call is two events, PreToolUse and PostToolUse, so the time reported for a call is the wall-clock time of
both processes together. Between the two events the script makes the change the call would have made (Edit:
one file rewritten; Bash: one file rewritten, as a `sed -i` would; Read: nothing). It does not run the agent or
the command itself: only the hook's share is measured.

Before the timed runs, one Bash call runs against the empty store: the first scan reads and copies every
project file. That call is reported on its own ("first Bash"), not mixed into the median.

    python3 bench/hook_overhead.py                     # prints the table, writes bench/results.json
    python3 bench/hook_overhead.py --write-readme      # also puts the table into README.md
    python3 bench/hook_overhead.py --files 50 --runs 3 --out /tmp/r.json   # a quick run

Stdlib only. The README and the site show only what this script wrote to bench/results.json, with the machine and
the date it ran on; tests/test_bench.py checks that.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
RESULTS = ROOT / "bench" / "results.json"
README = ROOT / "README.md"
TOOLS = ("Read", "Edit", "Bash")
START, END = "<!-- overhead:start -->", "<!-- overhead:end -->"


def make_project(d: Path, n: int) -> list[Path]:
    """n small text files in a git repository with one commit, 100 to a directory."""
    files = []
    for i in range(n):
        p = d / "src" / ("d%03d" % (i // 100)) / ("f%05d.py" % i)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join("value_%d_%d = %d\n" % (i, j, i * j) for j in range(8)), encoding="utf-8")
        files.append(p)
    git = ["git", "-C", str(d), "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-c", "commit.gpgsign=false"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "bench"], check=True)
    return files


def hook_ms(payload: dict, cwd: Path, env: dict) -> float:
    t = time.perf_counter()
    p = subprocess.run([sys.executable, "-m", "rewindagents", "hook"], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=cwd, env=env)
    ms = (time.perf_counter() - t) * 1000
    if p.returncode != 0 or p.stdout or p.stderr:
        raise SystemExit("hook did not run cleanly: %r" % ((p.returncode, p.stdout, p.stderr),))
    return ms


def call_ms(tool: str, target: Path, cwd: Path, env: dict, tag: str) -> float:
    """One tool call through the hook: PreToolUse, the call's own change, PostToolUse. Returns pre + post ms."""
    if tool == "Read":
        inp, resp = {"file_path": str(target)}, {"type": "text", "file": {"filePath": str(target)}}
    elif tool == "Edit":
        inp, resp = {"file_path": str(target), "old_string": "value", "new_string": "value"}, {"filePath": str(target)}
    else:
        rel = target.relative_to(cwd)
        inp, resp = {"command": "sed -i.bak s/1/2/ %s && rm %s.bak" % (rel, rel)}, {"stdout": "", "stderr": ""}
    base = {"session_id": "bench", "cwd": str(cwd), "tool_name": tool, "tool_input": inp, "tool_use_id": "toolu_" + tag}
    ms = hook_ms(dict(base, hook_event_name="PreToolUse"), cwd, env)
    if tool != "Read":
        with target.open("a", encoding="utf-8") as fh:
            fh.write("# %s\n" % tag)
    ms += hook_ms(dict(base, hook_event_name="PostToolUse", tool_response=resp), cwd, env)
    return ms


def stats(xs: list[float]) -> dict:
    s = sorted(xs)
    p90 = s[max(0, -(-len(s) * 9 // 10) - 1)]   # nearest rank
    mid = len(s) // 2
    median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    return {"median_ms": round(median, 1), "p90_ms": round(p90, 1), "min_ms": round(s[0], 1),
            "max_ms": round(s[-1], 1), "runs": len(s)}


def measure(n: int, runs: int, env: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp).resolve()
        files = make_project(d, n)
        first = call_ms("Bash", files[0], d, env, "first")
        out = {t: [] for t in TOOLS}
        for r in range(runs):
            for t in TOOLS:
                out[t].append(call_ms(t, files[(r * 7 + TOOLS.index(t)) % n], d, env, "%s%d" % (t, r)))
        return {"files": n, "first_bash_ms": round(first, 1), "tools": {t: stats(v) for t, v in out.items()}}


def startup_ms(env: dict, runs: int) -> dict:
    """The floor: a new interpreter importing the package and printing its version, no hook work."""
    xs = []
    for _ in range(runs):
        t = time.perf_counter()
        subprocess.run([sys.executable, "-m", "rewindagents", "--version"], capture_output=True, env=env, check=True)
        xs.append((time.perf_counter() - t) * 1000)
    return stats(xs)


def machine() -> dict:
    m = {"os": platform.system(), "os_release": platform.release(), "arch": platform.machine(),
         "cpus": os.cpu_count(), "python": platform.python_version()}
    if hasattr(os, "getloadavg"):   # other work on the machine moves the numbers; say how busy it was
        m["load_1m_at_start"] = round(os.getloadavg()[0], 1)
    if platform.system() == "Darwin":
        m["os_version"] = "macOS " + platform.mac_ver()[0]
        try:
            m["cpu"] = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                                      text=True, timeout=5).stdout.strip() or None
        except OSError:
            m["cpu"] = None
    return m


def commit() -> str | None:
    p = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip() or None if p.returncode == 0 else None


def run(sizes: list[int], runs: int) -> dict:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return {
        "date": datetime.datetime.now().astimezone().strftime("%Y-%m-%d"),
        "machine": machine(),
        "commit": commit(),
        "method": "wall-clock of the PreToolUse and PostToolUse hook processes for one call, python -m rewindagents "
                  "hook from the source tree, git repository of small text files; the script changes one file "
                  "between the events for Edit and Bash",
        "startup": startup_ms(env, runs),
        "results": [measure(n, runs, env) for n in sizes],
    }


def where(r: dict) -> str:
    m = r["machine"]
    host = m.get("os_version") or "%s %s" % (m["os"], m["os_release"])
    cpu = m.get("cpu") or m["arch"]
    load = "" if m.get("load_1m_at_start") is None else ", load average %s at the start" % m["load_1m_at_start"]
    return "%s, %s, %d CPUs, Python %s, on %s (commit %s%s)" % (host, cpu, m["cpus"], m["python"], r["date"],
                                                               r["commit"], load)


def table(r: dict) -> str:
    """The README table: median per call (p90 in brackets), in ms, one row per project size."""
    rows = ["| Project files | Read | Edit | Bash | First Bash (empty store) |", "|---:|---:|---:|---:|---:|"]
    for x in r["results"]:
        cells = ["%s (%s)" % (_ms(x["tools"][t]["median_ms"]), _ms(x["tools"][t]["p90_ms"])) for t in TOOLS]
        rows.append("| {:,} | {} | {} | {} | {} |".format(x["files"], *cells, _ms(x["first_bash_ms"])))
    return "\n".join(rows)


def _ms(v: float) -> str:
    return "{:,.0f} ms".format(v)


def readme_block(r: dict) -> str:
    runs = r["results"][0]["tools"]["Read"]["runs"]
    return "\n".join([
        START,
        "Measured by `bench/hook_overhead.py` on %s. Time the hook adds to one tool call: both hook processes (before "
        "and after the call), median of %d calls with the 90th percentile in brackets. A new Python process starting "
        "and importing the package takes %s of that (median). Raw numbers: `bench/results.json`."
        % (where(r), runs, _ms(r["startup"]["median_ms"])),
        "",
        table(r),
        "",
        "Other machines, disks and projects will differ; run `python3 bench/hook_overhead.py` to measure yours.",
        END,
    ])


def write_readme(r: dict, path: Path = README) -> None:
    text = path.read_text(encoding="utf-8")
    a, b = text.index(START), text.index(END) + len(END)
    path.write_text(text[:a] + readme_block(r) + text[b:], encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", type=int, nargs="+", default=[100, 1000, 10000])
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--write-readme", action="store_true")
    a = ap.parse_args(argv)
    r = run(a.files, a.runs)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
    print(where(r))
    print(table(r))
    if a.write_readme:
        write_readme(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
