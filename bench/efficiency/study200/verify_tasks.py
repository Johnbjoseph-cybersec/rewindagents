"""Check every study task before any agent run (no agent, no network).

For each task: the shipped repo must FAIL its visible tests and the hidden fix tests (there is a real bug),
and the repo with reference/ laid over it must PASS the visible tests, the hidden fix tests and the hidden
part-2 tests (the task is solvable and the hidden tests are not wrong). Run with python3 3.9 too: the agent's
`python3` may be either.

    python3 bench/efficiency/study200/verify_tasks.py [TASK ...]
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TASKS = Path(__file__).resolve().parent / "tasks"


def run_tests(test_dir, code_dir, files=None):
    with tempfile.TemporaryDirectory() as h:
        if files is None:
            src = Path(test_dir)
        else:
            for f in files:
                shutil.copy(Path(test_dir) / f, h)
            src = Path(h)
        env = dict(os.environ, PYTHONPATH=str(code_dir), PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(src), "-t", str(src)],
                           cwd=str(code_dir), env=env, capture_output=True, text=True, timeout=120)
        return r.returncode == 0, r.stderr[-1500:]


def check(task):
    out = []
    with tempfile.TemporaryDirectory() as t:
        orig = Path(t) / "orig"
        shutil.copytree(task / "repo", orig)
        ref = Path(t) / "ref"
        shutil.copytree(task / "repo", ref)
        for p in (task / "reference").rglob("*"):
            if p.is_file():
                dst = ref / p.relative_to(task / "reference")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, dst)
        res = {
            "orig visible fails": not run_tests(orig / "tests", orig)[0],
            "orig hidden-fix fails": not run_tests(task / "hidden", orig, ["test_hidden_fix.py"])[0],
            "ref visible passes": run_tests(ref / "tests", ref),
            "ref hidden-fix passes": run_tests(task / "hidden", ref, ["test_hidden_fix.py"]),
            "ref hidden-part2 passes": run_tests(task / "hidden", ref, ["test_hidden_part2.py"]),
        }
        ok = True
        for k, v in res.items():
            good = v if isinstance(v, bool) else v[0]
            ok &= good
            out.append("  %-26s %s" % (k, "ok" if good else "FAIL"))
            if not good and not isinstance(v, bool):
                out.append(v[1])
        for f in ("issue.md", "part2.md"):
            if not (task / f).is_file():
                ok = False
                out.append("  missing %s" % f)
    return ok, out


def main(argv):
    names = argv or sorted(p.name for p in TASKS.iterdir() if p.is_dir())
    bad = 0
    for n in names:
        ok, out = check(TASKS / n)
        print("%s %s" % ("PASS" if ok else "FAIL", n))
        print("\n".join(out))
        bad += not ok
    print("%d of %d tasks valid (python %s)" % (len(names) - bad, len(names), sys.version.split()[0]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
