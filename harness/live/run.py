#!/usr/bin/env python3
"""Live verification harness for rewindagents' seven supported coding-agent CLIs.

For each agent key in rewindagents.agents.AGENTS (claude, codex, cursor, gemini, copilot, droid, qwen) this
script:

1. detects the agent's CLI binary on PATH (the names rewindagents.init.BINARIES documents for that agent,
   the same table `rewindagents init` itself uses) and records its --version line;
2. when the binary is absent, writes NOT_INSTALLED evidence and does nothing else for that agent -- it never
   installs an agent CLI;
3. when the binary is present, creates a fresh scratch project in a new temp directory and runs the real
   `rewindagents install --agent <a> --settings <scratch>/<agent's project config path>` so the hook lands in
   a project-scoped config file this harness owns, never in a real agent config under the home directory;
4. runs the agent's own non-interactive ("headless") form with one tiny file-writing prompt, cwd=scratch,
   under a hard timeout -- started as the leader of its own process group (see `_run_isolated`) so that if
   it hangs *and* has forked a descendant of its own, the whole group is killed on timeout rather than just
   the one process subprocess.run would otherwise signal, leaving any forked descendant running as an orphan;
5. reads the scratch project's .rewindagents/log.jsonl and checks it holds at least one "pre" record and one
   "post" record for the step, then runs `rewindagents rewind 0 --dry-run` in the scratch project to exercise
   a checkpoint-restore plan;
6. writes harness/live/evidence/<agent>.json. VERIFIED_LIVE is used only when this run itself produced
   log_records > 0 and all three asserted flags true.

Before and after every agent's check, this script also reads (never writes) the sha256 of that agent's real,
home-directory config file -- the one `rewindagents init --global` would touch -- and records whether it
stayed byte-identical, because this harness must never be the thing that changes a user's real agent setup.
That result is both a stderr line on failure (kept, for a human watching the run) and an additive
`real_config_check: {"path": str, "unchanged": bool}` field on every evidence record, so the safety check's
result is part of the durable artifact, not only a conditional line of console output.

Every evidence record is also scrubbed, right before it is written to disk, of this machine's home-directory
prefix (`os.path.expanduser('~')`): any occurrence of that prefix inside `commands[]`, `scratch_dir`, or
`real_config_check["path"]` is replaced with the literal `~`. These are the only three fields a real run ever
puts an absolute filesystem path into. An evidence file is committed to the repo and read by anyone; it must
never embed the machine's real username in an absolute path (sprint-1 gate hygiene finding -- see
`docs/live-verification.md` and `harness/live/validate.py`, which rejects any evidence file where the scrub
did not happen).

Python standard library only. Run with the repo's own virtualenv and PYTHONPATH=src, from the repo root:

    PYTHONPATH=src .venv/bin/python harness/live/run.py --all
    PYTHONPATH=src .venv/bin/python harness/live/run.py --agent claude --agent codex
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rewindagents import agents as ra_agents  # noqa: E402
from rewindagents import init as ra_init  # noqa: E402

AGENT_KEYS: tuple[str, ...] = tuple(ra_agents.AGENTS)  # claude, codex, cursor, gemini, copilot, droid, qwen
HARD_TIMEOUT = 300  # was 120; 2026-11-18 Gemini API 503s with retry backoff pushed a passing run past 120 s
INSTALL_TIMEOUT = 30.0
REWIND_TIMEOUT = 30.0
VERSION_TIMEOUT = 10.0
PROMPT_TEMPLATE = (
    "Create a file named rewindagents-live-check.txt in the current directory containing exactly one line "
    "of text: live check for {agent}. Do not create, edit or delete any other file."
)
STATUSES = ("VERIFIED_LIVE", "NOT_INSTALLED", "INSTALL_BLOCKED", "RAN_NO_LOG", "FAILED")


def repo_python() -> str:
    """The interpreter this script itself is running under -- the repo venv, per the harness's own calling
    convention. Every `rewindagents` subprocess call below uses this same interpreter, so the hook command
    `install` writes into the scratch config and the one this script runs afterwards always agree."""
    return sys.executable


def rewindagents_env() -> dict[str, str]:
    """This process's environment with PYTHONPATH extended to include src/, so `python -m rewindagents ...`
    works from the clone without the package being installed."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing if existing else "")
    return env


def _display(argv: list[str], with_pythonpath: bool = False) -> str:
    prefix = f"PYTHONPATH={shlex.quote(str(SRC_DIR))} " if with_pythonpath else ""
    return prefix + shlex.join(argv)


def real_config_path(key: str) -> Path:
    """The agent's real, home-directory config file -- the one `rewindagents init --global` would write.
    Read-only here: this harness only ever installs into a scratch project's own config file."""
    return ra_init.target(key, root=REPO_ROOT, home=Path.home(), global_=True)


def _scrub_home(value: str | None) -> str | None:
    """Replace this machine's home-directory prefix (`os.path.expanduser('~')`) with the literal `~`
    anywhere it appears in `value`. `None` passes through unchanged. Used on every evidence string that can
    hold an absolute path (`commands[]`, `scratch_dir`, `real_config_check["path"]`) right before the
    evidence is written, so a committed evidence file never embeds the real username in an absolute path."""
    if value is None:
        return None
    home = os.path.expanduser("~")
    if not home or home == "~":
        return value  # nothing meaningful to strip (e.g. HOME unset) -- leave the string untouched
    return value.replace(home, "~")


def _scrub_evidence_paths(data: dict) -> dict:
    """Return a copy of an evidence dict with `_scrub_home` applied to every field a real run can put an
    absolute home-directory path into: `commands` (list of str), `scratch_dir` (str or None), and
    `real_config_check["path"]` (str). Every other field (status, log_records, agent_version, asserted,
    notes, ran_at, agent) is passed through byte-for-byte -- this function changes path prefixes only, never
    a factual field."""
    scrubbed = dict(data)
    scrubbed["commands"] = [_scrub_home(c) for c in data.get("commands", [])]
    scrubbed["scratch_dir"] = _scrub_home(data.get("scratch_dir"))
    rcc = data.get("real_config_check")
    if isinstance(rcc, dict) and "path" in rcc:
        rcc = dict(rcc)
        rcc["path"] = _scrub_home(rcc["path"])
        scrubbed["real_config_check"] = rcc
    return scrubbed


def _sha256_of(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_note(path: Path, before: str | None, after: str | None) -> str:
    if before is None and after is None:
        return f"real agent config {path}: absent before and after this run (never touched)"
    verdict = "unchanged" if before == after else "CHANGED -- this must not happen, stop and investigate"
    return f"real agent config {path}: sha256 before={before} after={after} ({verdict})"


def _run_isolated(cmd: list[str], *, cwd: Path | str | None = None, env: dict[str, str] | None = None,
                   timeout: float) -> subprocess.CompletedProcess:
    """subprocess.run, except the child is started as the leader of its own new process group *and* session
    (`start_new_session=True`, i.e. `setsid()`) and, on timeout, the harness kills that whole group with
    `os.killpg(SIGKILL)` instead of relying on subprocess.run's own timeout handling -- which only signals the
    one process it started via `Popen.kill()`. A CLI that forks a background worker (or backgrounds any
    descendant) and then either it or that descendant hangs would otherwise leave the descendant running as
    an orphan for the rest of its life, well after this harness has already written its evidence and moved
    on -- reproduced with a fake binary that backgrounds a long sleep and confirmed fixed in
    test_run.py:ProcessGroupKillTests.

    Raises subprocess.TimeoutExpired on timeout, with .stdout/.stderr attached same as subprocess.run, so
    every existing `except subprocess.TimeoutExpired` call site below needs no other change."""
    # stdin is closed: `codex exec` (0.170) otherwise waits for "additional input from stdin" and hangs to the
    # hard timeout when the harness itself runs without a terminal (found live 2026-11-18).
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as e:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass  # the group leader (or the whole group) is already gone -- nothing left to kill
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # SIGKILL to a stuck group should never need this, but never let the harness itself hang here
            proc.kill()
            stdout, stderr = proc.communicate()
        e.stdout, e.stderr = stdout, stderr
        raise


def _probe_version(binary: str, commands: list[str]) -> str | None:
    cmd = [binary, "--version"]
    commands.append(_display(cmd))
    try:
        r = _run_isolated(cmd, timeout=VERSION_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [ln for ln in (r.stdout or r.stderr or "").splitlines() if ln.strip()]
    return lines[0].strip() if lines else None


def _read_log(path: Path) -> list[dict]:
    """Every parsed JSON record in the log, in file order. A torn-write fragment (log.py's docstring: a line
    that is not valid JSON) is skipped rather than raising -- the harness reports what it can read."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


# Headless ("print and exit") forms, one per agent. claude's is run live on this machine and verified by this
# harness every time it runs. The other six are written from each vendor's published CLI docs the same way
# rewindagents.agents module sources its hook payloads, but -- unlike that module's forms -- they have never
# been run here: no binary for them exists on this machine (checked below with shutil.which). If one is later
# installed, the harness will actually run the command below, read the real log and report VERIFIED_LIVE,
# RAN_NO_LOG or FAILED from what it observes -- never a status assumed in advance.
def _claude_cmd(binary: str, prompt: str) -> list[str]:
    # claude --help (read 2026-11-18): -p/--print for a non-interactive run; --permission-mode bypassPermissions
    # skips the interactive approval prompt for the Write/Edit/Bash tools; --setting-sources project loads only
    # this scratch project's .claude/settings.json, not this machine's real user settings.
    return [binary, "-p", prompt, "--permission-mode", "bypassPermissions", "--setting-sources", "project",
            "--output-format", "json"]


def _codex_cmd(binary: str, prompt: str) -> list[str]:
    # developers.openai.com/codex/cli, read 2026-11-18 (NOT run on this machine: codex is not installed here).
    # `codex exec PROMPT` runs one prompt non-interactively. Run live 2026-11-18 (codex-cli 0.170.0): --full-auto
    # is gone (use -s workspace-write); project config, including .codex/hooks.json, loads only with --trust; and
    # a hook runs only after it has been reviewed, which a user does once interactively. A fresh scratch project
    # has no review on record, so this run passes --dangerously-bypass-hook-trust (that one invocation only).
    return [binary, "exec", "--trust", "--dangerously-bypass-hook-trust", "--skip-git-repo-check",
            "-s", "workspace-write", prompt]  # the scratch project is not a git repository


def _cursor_cmd(binary: str, prompt: str) -> list[str]:
    # cursor.com/docs/cli, read 2026-11-18 (NOT run here: cursor-agent is not installed). `-p` prints and exits;
    # --force skips the confirmation a file-writing command would otherwise ask for.
    return [binary, "-p", prompt, "--force"]


def _gemini_cmd(binary: str, prompt: str) -> list[str]:
    # geminicli.com/docs, read 2026-11-18 (NOT run here: gemini is not installed). `-p` prints and exits;
    # --yolo auto-accepts every tool call instead of prompting. Run live 2026-11-18 (gemini 0.68.0): a headless run
    # refuses an untrusted folder, and --skip-trust runs it WITHOUT loading the project's .gemini/settings.json, so
    # the project hook never fires. GEMINI_CLI_TRUST_WORKSPACE=true trusts the scratch folder, which is what a user
    # does once interactively; with it the hook ran and recorded the step.
    return ["env", "GEMINI_CLI_TRUST_WORKSPACE=true", binary, "-p", prompt, "--yolo"]


def _copilot_cmd(binary: str, prompt: str) -> list[str]:
    # docs.github.com/en/copilot, read 2026-11-18 (NOT run here: copilot is not installed). `-p` prints and
    # exits; --allow-all-tools removes the interactive approval for every tool the run might use. Run live
    # 2026-11-18 (copilot 1.0.114): without --trust-folder an untrusted scratch project's .github/hooks are not
    # loaded and nothing is recorded; --trust-folder trusts it for this one prompt-mode session only.
    return [binary, "-p", prompt, "--allow-all-tools", "--trust-folder"]


def _droid_cmd(binary: str, prompt: str) -> list[str]:
    # docs.factory.com/cli, read 2026-11-18 (NOT run here: droid is not installed). `droid exec PROMPT` is the
    # headless form; --auto medium lets file edits through without an interactive approval.
    return [binary, "exec", prompt, "--auto", "medium"]


def _qwen_cmd(binary: str, prompt: str) -> list[str]:
    # github.com/QwenLM/qwen-code docs, read 2026-11-18 (NOT run here: qwen is not installed). Qwen Code forked
    # Gemini CLI and keeps the same flags: `-p` prints and exits, --yolo auto-accepts every tool call.
    return [binary, "-p", prompt, "--yolo"]


HEADLESS: dict[str, Callable[[str, str], list[str]]] = {
    "claude": _claude_cmd, "codex": _codex_cmd, "cursor": _cursor_cmd, "gemini": _gemini_cmd,
    "copilot": _copilot_cmd, "droid": _droid_cmd, "qwen": _qwen_cmd,
}


def _evidence(agent: str, status: str, version: str | None, ran_at: str, scratch_dir: str | None,
              commands: list[str], log_records: int, asserted: dict[str, bool], notes: str) -> dict:
    assert status in STATUSES, status
    return {
        "agent": agent, "status": status, "agent_version": version, "ran_at": ran_at,
        "scratch_dir": scratch_dir, "commands": commands, "log_records": log_records,
        "asserted": asserted, "notes": notes,
    }


def check_agent(key: str) -> dict:
    """Run every step for one agent and return its evidence dict, with an additive `real_config_check` field
    attached (see `_check_agent_core`'s docstring for the rest of what this records). Reads (never writes)
    the sha256 of the agent's real, home-directory config file -- the one `rewindagents init --global` would
    touch -- before and after `_check_agent_core` runs, because this harness must never be the thing that
    changes a user's real agent setup. The comparison is both a stderr line on failure (for a human watching
    the run) and a durable `real_config_check: {"path": str, "unchanged": bool}` field on the evidence record
    itself, so the safety check's result is part of the artifact, not only conditional console output."""
    real_cfg = real_config_path(key)
    sha_before = _sha256_of(real_cfg)
    data = _check_agent_core(key)
    sha_after = _sha256_of(real_cfg)
    note = _sha_note(real_cfg, sha_before, sha_after)
    if "CHANGED" in note:
        print(f"SAFETY VIOLATION: {note}", file=sys.stderr)
    data["real_config_check"] = {"path": str(real_cfg), "unchanged": sha_before == sha_after}
    return data


def _check_agent_core(key: str) -> dict:
    """Run every step for one agent and return its evidence dict (minus `real_config_check`, which the
    `check_agent` wrapper attaches). Never raises: any unexpected failure in the middle of a check is caught
    and turned into an honest FAILED evidence record (with the exception text in notes), so one agent
    misbehaving does not stop the harness from checking the other six."""
    commands: list[str] = []
    notes: list[str] = []
    ran_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    no_asserted = {"pre_event": False, "post_event": False, "checkpoint_restored": False}

    try:
        binary_names = ra_init.BINARIES[key]
        binary = next((p for name in binary_names if (p := shutil.which(name))), None)
        if binary is None:
            notes.append(f"no binary found on PATH among: {', '.join(binary_names)}")
            return _evidence(key, "NOT_INSTALLED", None, ran_at, None, commands, 0, no_asserted,
                              "; ".join(notes))

        version = _probe_version(binary, commands)
        scratch = Path(tempfile.mkdtemp(prefix=f"rewindagents-live-{key}-"))
        ag = ra_agents.AGENTS[key]
        settings_path = scratch / ag.settings   # project-scoped only; never a path under the home directory

        install_cmd = [repo_python(), "-m", "rewindagents", "install", "--agent", key, "--settings",
                        str(settings_path)]
        commands.append(_display(install_cmd, with_pythonpath=True))
        r = _run_isolated(install_cmd, cwd=scratch, env=rewindagents_env(), timeout=INSTALL_TIMEOUT)
        if r.returncode != 0:
            notes.append(f"install exited {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}")
            return _evidence(key, "INSTALL_BLOCKED", version, ran_at, str(scratch), commands, 0, no_asserted,
                              "; ".join(notes))
        if not settings_path.is_file():
            notes.append("install reported success but wrote no project-scoped config file")
            return _evidence(key, "INSTALL_BLOCKED", version, ran_at, str(scratch), commands, 0, no_asserted,
                              "; ".join(notes))

        prompt = PROMPT_TEMPLATE.format(agent=key)
        headless_cmd = HEADLESS[key](binary, prompt)
        commands.append(_display(headless_cmd))
        timed_out = False
        try:
            _run_isolated(headless_cmd, cwd=scratch, timeout=HARD_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            notes.append(f"agent invocation did not finish within the {HARD_TIMEOUT:g}s hard timeout "
                         "(its whole process group was killed)")
        except OSError as e:
            notes.append(f"agent invocation could not be run: {e}")
            return _evidence(key, "FAILED", version, ran_at, str(scratch), commands, 0, no_asserted,
                              "; ".join(notes))

        log_path = scratch / ".rewindagents" / "log.jsonl"
        records = _read_log(log_path)
        log_records = len(records)
        has_pre = any(rec.get("event") == "pre" for rec in records)
        has_post = any(rec.get("event") == "post" for rec in records)

        checkpoint_restored = False
        if records:
            session = records[-1].get("session")
            rewind_cmd = [repo_python(), "-m", "rewindagents", "rewind", "0", "--dry-run"]
            if isinstance(session, str) and session:
                rewind_cmd += ["--session", session]
            commands.append(_display(rewind_cmd, with_pythonpath=True))
            try:
                rr = _run_isolated(rewind_cmd, cwd=scratch, env=rewindagents_env(), timeout=REWIND_TIMEOUT)
                plan = rr.stdout or ""
                checkpoint_restored = rr.returncode in (0, 1) and "rewind to step" in plan
                if not checkpoint_restored:
                    tail = plan.strip()[:300] or (rr.stderr or "").strip()[:300]
                    notes.append(f"rewind --dry-run did not produce a restore plan (exit {rr.returncode}): {tail}")
            except subprocess.TimeoutExpired:
                notes.append(f"rewind --dry-run did not finish within {REWIND_TIMEOUT:g}s")

        asserted = {"pre_event": has_pre, "post_event": has_post, "checkpoint_restored": checkpoint_restored}
        if timed_out:
            status = "FAILED"
        elif log_records == 0:
            status = "RAN_NO_LOG"
            notes.append("agent invocation finished but .rewindagents/log.jsonl in the scratch project has no "
                         "records: either the hook never fired or the agent made no tool call")
        elif has_pre and has_post and checkpoint_restored:
            status = "VERIFIED_LIVE"
        else:
            status = "FAILED"
            notes.append(f"log has {log_records} record(s) but the assertion is incomplete: "
                         f"pre_event={has_pre} post_event={has_post} checkpoint_restored={checkpoint_restored}")
        return _evidence(key, status, version, ran_at, str(scratch), commands, log_records, asserted,
                          "; ".join(notes))
    except Exception as e:  # noqa: BLE001 -- deliberate: one agent's unexpected failure must not stop the rest
        notes.append(f"unexpected error during the check: {type(e).__name__}: {e}")
        return _evidence(key, "FAILED", None, ran_at, None, commands, 0, no_asserted, "; ".join(notes))


def _write_evidence(data: dict) -> Path:
    data = _scrub_evidence_paths(data)  # strip this machine's home-dir prefix before anything hits disk
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{data['agent']}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run each supported coding-agent CLI live against a scratch project with rewindagents "
                    "hooks installed, and write one evidence JSON per agent under harness/live/evidence/.")
    ap.add_argument("--all", action="store_true", help="check every supported agent (the default)")
    ap.add_argument("--agent", action="append", choices=AGENT_KEYS, metavar="NAME",
                    help="check only this agent (repeat for more); default is every agent")
    args = ap.parse_args(argv)
    keys = args.agent if args.agent else list(AGENT_KEYS)

    exit_code = 0
    for key in keys:
        print(f"== {key} ==")
        data = check_agent(key)
        path = _write_evidence(data)
        print(f"  status: {data['status']}")
        if data["notes"]:
            print(f"  notes: {data['notes']}")
        print(f"  evidence: {path}")
        if data["status"] == "FAILED":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
