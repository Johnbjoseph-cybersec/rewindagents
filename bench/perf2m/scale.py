"""Time the hook around a Bash call in a big git repository, and prove rewind restores an rm and a sed -i.

    python3 scale.py <repo> <label> [--runs 7] [--full] [--out file.json] [--tracked-a REL] [--tracked-b REL]

--full runs the old whole-project scan (REWINDAGENTS_BASH_SCAN=full) for comparison. Time per call is the
wall-clock of the Pre and the Post hook process together, as bench/hook_overhead.py measures it. The repo gets
a .rewindagents store; the script removes it and restores the files it touched when it is done."""
import argparse, hashlib, json, os, shutil, statistics, subprocess, sys, time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent.parent / "src"
ap = argparse.ArgumentParser()
ap.add_argument("repo"); ap.add_argument("label"); ap.add_argument("--runs", type=int, default=7)
ap.add_argument("--full", action="store_true"); ap.add_argument("--out")
ap.add_argument("--a", default="d000/s00/f0000.txt"); ap.add_argument("--b", default="d000/s00/f0001.txt")
ap.add_argument("--rm", default="d001/s01/f0010.txt"); ap.add_argument("--sed", default="d001/s01/f0011.txt")
ap.add_argument("--cold-stop", action="store_true", help="stop git's fsmonitor daemon first (a cold start)")
a = ap.parse_args()
repo = Path(a.repo).resolve()
env = dict(os.environ, PYTHONPATH=str(SRC), **({"REWINDAGENTS_BASH_SCAN": "full"} if a.full else {}))


def hook(payload):
    t = time.perf_counter()
    p = subprocess.run([sys.executable, "-m", "rewindagents", "hook"], input=json.dumps(payload), text=True,
                       capture_output=True, cwd=repo, env=env)
    assert p.returncode == 0 and not p.stderr, p.stderr
    return (time.perf_counter() - t) * 1000


def call(tool, inp, change, n, session="bench"):
    base = {"session_id": session, "cwd": str(repo), "tool_name": tool, "tool_input": inp, "tool_use_id": f"{session}-{tool}-{n}"}
    t = hook(dict(base, hook_event_name="PreToolUse"))
    change()
    t += hook(dict(base, hook_event_name="PostToolUse", tool_response={"ok": True}))
    return t


def sed(rel, n):
    p = repo / rel
    p.write_text(f"edit {n}\n")


git = lambda *x: subprocess.run(["git", "-C", str(repo), *x], capture_output=True, text=True).stdout
def stop_daemon():
    subprocess.run(["git", "-C", str(repo), "fsmonitor--daemon", "stop"], capture_output=True)


res = {"label": a.label, "repo": str(repo), "path": "full" if a.full else "git", "tracked": int(git("ls-files", "-z").count("\0")) if False else None}
store = repo / ".rewindagents"
shutil.rmtree(store, ignore_errors=True)
if a.cold_stop:
    stop_daemon()
cmd = {"command": f"sed -i s/x/y/ {a.a}"}
res["load"] = os.getloadavg()[0]
res["first_bash_ms"] = round(call("Bash", cmd, lambda: sed(a.a, 0), 0), 1)
bash = [call("Bash", cmd, lambda i=i: sed(a.a, i), i) for i in range(1, a.runs + 1)]
res["bash_ms"] = [round(x, 1) for x in bash]; res["bash_median_ms"] = round(statistics.median(bash), 1)
read = [call("Read", {"file_path": str(repo / a.b)}, lambda: None, i) for i in range(a.runs)]
res["read_median_ms"] = round(statistics.median(read), 1)
edit = [call("Edit", {"file_path": str(repo / a.b), "old_string": "e", "new_string": "E"}, lambda i=i: sed(a.b, i), i) for i in range(a.runs)]
res["edit_median_ms"] = round(statistics.median(edit), 1)

# rewind proof: rm one file, sed -i another, rewind to before the step
shutil.rmtree(store, ignore_errors=True)
rm_rel, sed_rel = a.rm, a.sed
orig_sed = (repo / sed_rel).read_bytes()
(repo / sed_rel).write_text("original content of the sed target\n")
subprocess.run(["git", "-C", str(repo), "update-index", "--add", sed_rel], check=True)  # tracked, content differs from HEAD's empty blob: dirty before
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
before = {r: (sha(repo / r), (repo / r).stat().st_mode & 0o777 if (repo / r).exists() else None) for r in (rm_rel, sed_rel)}
cmd = {"command": f"rm {rm_rel}; sed -i s/original/changed/ {sed_rel}"}
def change():
    (repo / rm_rel).unlink()
    (repo / sed_rel).write_text("changed content of the sed target\n")
t = call("Bash", cmd, change, 99, "proof")
res["proof_call_ms"] = round(t, 1)
mid = {r: sha(repo / r) for r in (rm_rel, sed_rel)}
r = subprocess.run([sys.executable, "-m", "rewindagents", "rewind", "0", "--session", "proof"], capture_output=True, text=True, cwd=repo, env=env)
after = {r_: (sha(repo / r_), (repo / r_).stat().st_mode & 0o777 if (repo / r_).exists() else None) for r_ in (rm_rel, sed_rel)}
recs = [json.loads(l) for l in (store / "log.jsonl").read_text().splitlines() if '"proof"' in l]
res["proof"] = {"rm": rm_rel, "sed": sed_rel, "after_command_rm_exists": mid[rm_rel] is not None, "restored_equal": after == before,
                "rewind_rc": r.returncode, "rewind_out": (r.stdout + r.stderr).strip().splitlines()[:6],
                "checkpoints": [Path(c["path"]).name for c in recs[-1]["args"].get("checkpoints", [])]}
# put the repo back
subprocess.run(["git", "-C", str(repo), "reset", "-q", "--", sed_rel], capture_output=True)
for rel in (a.a, a.b, sed_rel):
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", rel], capture_output=True)
shutil.rmtree(store, ignore_errors=True)
print(json.dumps(res, indent=1))
if a.out:
    Path(a.out).write_text(json.dumps(res, indent=1))
