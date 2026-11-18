"""One scripted session on a mid-size git repo (default 10,000 files), once with the old whole-project scan
(REWINDAGENTS_BASH_SCAN=full) and once with the git path; compare the checkpoints and the rewind result.

    python3 bench/perf2m/compare_scan_paths.py [files]
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent.parent / "src"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000


def run(args, d, env=None, inp=None):
    return subprocess.run(args, input=inp, text=True, capture_output=True, cwd=d, env=dict(os.environ, PYTHONPATH=str(SRC), **(env or {})))


def build(d):
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    run(["git", "init", "-q"], d)
    for i in range(N):
        p = Path(d, f"src/d{i // 100:03d}/f{i:05d}.py"); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"v = {i}\n")
    Path(d, "run.sh").write_text("#!/bin/sh\necho hi\n"); os.chmod(Path(d, "run.sh"), 0o755)
    Path(d, ".gitignore").write_text(".env\n*.log\nbuild/\n")
    Path(d, ".env").write_text("K=1\n"); Path(d, "app.log").write_text("log\n")
    os.makedirs(Path(d, "build")); Path(d, "build/out.bin").write_text("o\n")
    run(g + ["add", "-A"], d); run(g + ["commit", "-qm", "i"], d)
    Path(d, "src/d000/f00005.py").write_text("v = 5  # dirty before\n")                 # tracked, dirty before
    Path(d, "scratch.txt").write_text("untracked before\n")                                # untracked before
    Path(d, "src/d000/f00006.py").write_text("v = 6  # staged\n"); run(g + ["add", "src/d000/f00006.py"], d)  # staged...


def hook(d, env, name, cmd, tid, resp=None):
    pl = {"hook_event_name": name, "session_id": "S1", "cwd": d, "tool_name": "Bash", "tool_input": {"command": cmd}, "tool_use_id": tid}
    if resp is not None: pl["tool_response"] = resp
    p = run([sys.executable, "-m", "rewindagents", "hook"], d, env, json.dumps(pl))
    assert p.returncode == 0, p.stderr


def tree(d):
    """Every file but the store, .git and the ignored directory build/ (a file made there is not checkpointed, by rule)."""
    return {str(p.relative_to(d)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777)
            for p in sorted(Path(d).rglob("*")) if p.is_file() and not {".rewindagents", ".git", "build"} & set(p.relative_to(d).parts)}


def session(env):
    d = str(Path(tempfile.mkdtemp()).resolve() / "proj"); os.mkdir(d)
    build(d)
    before = tree(d)
    cmd = "rm src/d001/f00100.py; sed -i.bak s/7/77/ src/d000/f00007.py; echo new > created.txt; git mv src/d002/f00200.py moved.py; echo '# again' >> src/d000/f00006.py; echo more >> src/d000/f00005.py; echo more >> scratch.txt; rm .env; echo x >> app.log; chmod -x run.sh; rm scratch2.txt 2>/dev/null; echo b > build/new.bin"
    hook(d, env, "PreToolUse", cmd, "b1")
    for sh in ("rm -f src/d001/f00100.py", "sed -i.bak s/7/77/ src/d000/f00007.py", "echo new > created.txt", "git mv src/d002/f00200.py moved.py",
               "echo '# again' >> src/d000/f00006.py", "echo more >> src/d000/f00005.py", "echo more >> scratch.txt", "rm .env",
               "echo x >> app.log", "chmod -x run.sh", "echo b > build/new.bin"):
        subprocess.run(["sh", "-c", sh], cwd=d, check=True)
    hook(d, env, "PostToolUse", cmd, "b1", {"ok": 1})
    recs = [json.loads(l) for l in Path(d, ".rewindagents/log.jsonl").read_text().splitlines()]
    post = recs[-1]["args"]
    cps = sorted(json.dumps(c, sort_keys=True).replace(d, "<D>") for c in post["checkpoints"])
    afters = sorted(json.dumps(c, sort_keys=True).replace(d, "<D>") for c in post["after"])
    pre = recs[0]["args"]["bash_scan"]
    after = tree(d)
    r = run([sys.executable, "-m", "rewindagents", "rewind", "0", "--session", "S1"], d)
    return dict(d=d, cps=cps, afters=afters, pre=pre, scan=post["bash_scan"], rc=r.returncode, restored=tree(d), before=before, after=after,
                out=r.stdout.replace(d, "<D>") + r.stderr.replace(d, "<D>"))


old = session({"REWINDAGENTS_BASH_SCAN": "full"})
new = session({"REWINDAGENTS_BASH_SCAN": "git"})
print("pre record old:", old["pre"], " new:", new["pre"])
print("checkpoints: old %d new %d identical: %s" % (len(old["cps"]), len(new["cps"]), old["cps"] == new["cps"]))
print("after entries identical:", old["afters"] == new["afters"])
print("changed counts:", old["scan"], new["scan"])
print("rewind rc old/new:", old["rc"], new["rc"], " text identical:", old["out"] == new["out"])
print("old path restored == original:", old["restored"] == old["before"], "; git path restored == original:", new["restored"] == new["before"])
for c in new["cps"]: print("  ", c[:150])
ok = old["cps"] == new["cps"] and old["afters"] == new["afters"] and new["restored"] == new["before"] and old["restored"] == old["before"]
print("RESULT:", "IDENTICAL" if ok else "DIFFERENT")
if not ok:
    print("only old:", set(old["cps"]) - set(new["cps"])); print("only new:", set(new["cps"]) - set(old["cps"]))
    print("diff restored:", {k for k in new["before"] if new["restored"].get(k) != new["before"][k]}, {k for k in new["restored"] if k not in new["before"]})
