"""Run the same scripted session through the old and the new hook; compare the records and the rewind result.

    python3 bench/perf10x/compare_old_new.py <old src dir> <new src dir>
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

OLD, NEW = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()


def hook(src, d, payload, agent=None):
    argv = [sys.executable, "-m", "rewindagents", "hook"] + (["--agent", agent] if agent else [])
    p = subprocess.run(argv, input=json.dumps(payload), text=True, capture_output=True, cwd=d,
                       env=dict(os.environ, PYTHONPATH=str(src)))
    return p.returncode, p.stdout, p.stderr


def cli(src, d, *a):
    return subprocess.run([sys.executable, "-m", "rewindagents", *a], text=True, capture_output=True, cwd=d,
                          env=dict(os.environ, PYTHONPATH=str(src)))


def session(src, d):
    g = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(g[:3] + ["init", "-q"], check=True)
    for n in range(20):
        Path(d, f"f{n}.py").write_text(f"x = {n}\n")
    Path(d, "run.sh").write_text("#!/bin/sh\necho hi\n"); os.chmod(Path(d, "run.sh"), 0o755)
    Path(d, ".env").write_text("K=1\n"); Path(d, ".gitignore").write_text(".env\n")
    subprocess.run(g + ["add", "-A"], check=True); subprocess.run(g + ["commit", "-qm", "i"], check=True)
    out = []
    def ev(name, tool, inp, resp=None, **kw):
        pl = {"hook_event_name": name, "session_id": "S1", "cwd": d, "tool_name": tool, "tool_input": inp,
              "tool_use_id": kw.pop("tid", None) or "tid-" + tool}
        if resp is not None: pl["tool_response"] = resp
        out.append(hook(src, d, pl, **kw))
    ev("PreToolUse", "Read", {"file_path": d + "/f1.py"}); ev("PostToolUse", "Read", {"file_path": d + "/f1.py"}, "x = 1")
    ev("PreToolUse", "Edit", {"file_path": d + "/f2.py", "old_string": "2", "new_string": "22"})
    Path(d, "f2.py").write_text("x = 22\n")
    ev("PostToolUse", "Edit", {"file_path": d + "/f2.py", "old_string": "2", "new_string": "22"}, {"ok": True})
    ev("PreToolUse", "Write", {"file_path": d + "/new.py", "content": "y" * 5000})
    Path(d, "new.py").write_text("y" * 5000)
    ev("PostToolUse", "Write", {"file_path": d + "/new.py", "content": "y" * 5000}, "ok")
    cmd = {"command": "rm f3.py .env; sed -i.bak s/1/9/ f4.py; chmod -x run.sh; echo n > made.txt"}
    ev("PreToolUse", "Bash", cmd, tid="b1")
    os.remove(Path(d, "f3.py")); os.remove(Path(d, ".env")); Path(d, "f4.py").write_text("x = 9\n")
    os.chmod(Path(d, "run.sh"), 0o644); Path(d, "made.txt").write_text("n\n")
    ev("PostToolUse", "Bash", cmd, {"stdout": "z" * 6000}, tid="b1")
    ev("preToolUse", "Shell", {"command": "ls"}, agent="cursor"); ev("postToolUse", "Shell", {"command": "ls"}, agent="cursor")
    ev("BeforeTool", "run_shell_command", {"command": "ls"}, agent="gemini")
    out.append(hook(src, d, {"bad": 1}))
    out.append(hook(src, d, {"hook_event_name": "PreToolUse", "cwd": "/nonexistent-dir-x", "tool_name": "Read"}))
    return out


def norm(d):
    recs = [json.loads(l) for l in Path(d, ".rewindagents", "log.jsonl").read_text().splitlines()]
    for r in recs:
        for k in ("ts", "hash", "prev"): r.pop(k)
    return json.loads(json.dumps(recs).replace(d, "<D>"))


def tree(d):
    return {str(p.relative_to(d)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777)
            for p in sorted(Path(d).rglob("*")) if p.is_file() and ".rewindagents" not in p.parts and ".git" not in p.parts}


res = {}
for tag, src in (("old", OLD), ("new", NEW)):
    d = str(Path(tempfile.mkdtemp()).resolve() / "proj"); os.mkdir(d)
    # same directory name for both runs so recorded paths compare equal after replacing the temp root
    outs = session(src, d)
    v = cli(src, d, "verify")
    res[tag] = dict(d=d, outs=[(o[0], o[1], o[2].split(":")[0]) for o in outs], recs=norm(d), verify=(v.returncode, v.stdout.strip()),
                    before=tree(d))
a, b = res["old"], res["new"]
print("exit codes + stdout old/new equal:", [(x[0], x[1]) for x in a["outs"]] == [(x[0], x[1]) for x in b["outs"]])
print("records:", len(a["recs"]), len(b["recs"]), "structurally equal:", a["recs"] == b["recs"])
print("verify old:", a["verify"], "new:", b["verify"])
print("stderr heads equal:", [x[2] for x in a["outs"]] == [x[2] for x in b["outs"]])
# rewind to step 3 (before the Bash call, which deleted f3.py and .env, changed f4.py, dropped +x, made made.txt)
for tag, src in (("old", OLD), ("new", NEW)):
    d = res[tag]["d"]
    r = cli(src, d, "rewind", "3", "--session", "S1")
    res[tag]["rewind"] = (r.returncode, (r.stdout + r.stderr).replace(d, "<D>")[-400:])
    res[tag]["after_rewind"] = tree(d)
    res[tag]["restored"] = [Path(d, "f3.py").exists(), Path(d, ".env").exists(), Path(d, "made.txt").exists(),
                            oct(Path(d, "run.sh").stat().st_mode & 0o777), Path(d, "f4.py").read_text()]
print("rewind 3 rc old/new:", res["old"]["rewind"][0], res["new"]["rewind"][0])
print("restored (f3 back, .env back, made.txt present, run.sh mode, f4) old/new:", res["old"]["restored"], res["new"]["restored"])
print("restored trees identical:", res["old"]["after_rewind"] == res["new"]["after_rewind"], "(%d files)" % len(res["new"]["after_rewind"]))
print("pre-rewind trees identical:", a["before"] == b["before"])
ok = (a["recs"] == b["recs"] and a["verify"][0] == 0 == b["verify"][0] and a["after_rewind"] == b["after_rewind"]
      and a["rewind"][0] == b["rewind"][0] == 1  # 1 = rewound, plus the note about the unscanned Cursor/Gemini step
      and a["restored"] == b["restored"] == [True, True, False, "0o755", "x = 4\n"])
print("RESULT:", "IDENTICAL" if ok and [(x[0], x[1]) for x in a["outs"]] == [(x[0], x[1]) for x in b["outs"]] else "DIFFERENT")
if not ok:
    print(res["old"]["rewind"], res["new"]["rewind"])
else:
    print("rewind text identical:", res["old"]["rewind"][1] == res["new"]["rewind"][1])
