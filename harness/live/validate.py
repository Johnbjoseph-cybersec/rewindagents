#!/usr/bin/env python3
"""Schema-check every file under harness/live/evidence/ against the LIVE-HARNESS EVIDENCE SCHEMA.

Checks, per agent key in rewindagents.agents.AGENTS:
- the evidence file exists and parses as one JSON object;
- every required field is present with the right type;
- "status" is one of the five allowed values, and "agent" inside the file matches the file name;
- "asserted" has exactly the three required boolean flags;
- "real_config_check" has exactly the required {"path": str, "unchanged": bool} shape;
- VERIFIED_LIVE is internally consistent: log_records > 0, all three asserted flags true, "commands" is
  non-empty, "scratch_dir" is not null, and at least one command string names the agent's own binary (from
  rewindagents.init.BINARIES) -- a VERIFIED_LIVE claim with no commands and no scratch directory recorded is
  exactly the fabrication shape this check exists to catch, regardless of what the boolean flags say;
- NOT_INSTALLED is internally consistent: log_records == 0 and all three asserted flags false (nothing ran);
- no evidence file embeds this machine's real username in an absolute path: "commands", "scratch_dir" and
  "real_config_check.path" must never contain a literal "/Users/" or "/home/" segment -- harness/live/run.py
  scrubs `os.path.expanduser('~')` to "~" in exactly these three fields before writing evidence, and this is
  the check that catches a committed evidence file where that scrub did not happen (sprint-1 gate hygiene
  finding).

With no arguments, checks the hardcoded AGENT_KEYS x EVIDENCE_DIR list (every agent's own evidence file
under harness/live/evidence/). Given one or more paths on the command line -- e.g. a shell-expanded
`harness/live/evidence/*.json`, or any other file -- checks exactly those paths instead, deriving each
file's expected agent key from its filename stem (sprint-2 hygiene finding: `main()` used to ignore its
arguments entirely and always re-check the hardcoded list regardless of what was passed on the command
line, so running it against a corrupted copy or a nonexistent path silently printed "OK").

Prints one line per violation and exits 1 if there were any, 0 otherwise. Python standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rewindagents import agents as ra_agents  # noqa: E402
from rewindagents import init as ra_init  # noqa: E402

AGENT_KEYS = tuple(ra_agents.AGENTS)
STATUSES = ("VERIFIED_LIVE", "NOT_INSTALLED", "INSTALL_BLOCKED", "RAN_NO_LOG", "FAILED")
REQUIRED_FIELDS = {
    "agent": str, "status": str, "agent_version": (str, type(None)), "ran_at": str,
    "scratch_dir": (str, type(None)), "commands": list, "log_records": int, "asserted": dict, "notes": str,
    "real_config_check": dict,
}
ASSERTED_FIELDS = ("pre_event", "post_event", "checkpoint_restored")
REAL_CONFIG_CHECK_FIELDS = {"path": str, "unchanged": bool}
HOME_PATH_MARKERS = ("/Users/", "/home/")


def _has_unscrubbed_home_path(text: str) -> bool:
    """True if `text` contains a literal "/Users/" or "/home/" path segment -- the shape an un-scrubbed
    absolute home-directory path always has on macOS or Linux. `harness/live/run.py` replaces this
    machine's home-directory prefix with "~" before writing evidence; a file that still has one of these
    markers means that scrub never ran, or ran against the wrong fields."""
    return any(marker in text for marker in HOME_PATH_MARKERS)


def validate_one(agent: str, path: Path) -> list[str]:
    problems: list[str] = []
    if not path.is_file():
        return [f"{agent}: missing evidence file {path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"{agent}: cannot read {path}: {e}"]
    try:
        data = json.loads(text)
    except ValueError as e:
        return [f"{agent}: {path} is not valid JSON: {e}"]
    if not isinstance(data, dict):
        return [f"{agent}: {path} does not hold a JSON object"]

    for field, kind in REQUIRED_FIELDS.items():
        if field not in data:
            problems.append(f"{agent}: missing field {field!r}")
            continue
        if not isinstance(data[field], kind):
            problems.append(f"{agent}: field {field!r} has type {type(data[field]).__name__}, expected {kind}")
    if problems:   # the checks below assume every field is present with the right shape
        return problems

    if data["agent"] != agent:
        problems.append(f"{agent}: field 'agent' is {data['agent']!r}, expected {agent!r} (file name mismatch)")
    if data["status"] not in STATUSES:
        problems.append(f"{agent}: status {data['status']!r} is not one of {STATUSES}")
    if data["log_records"] < 0:
        problems.append(f"{agent}: log_records is negative ({data['log_records']})")
    if not all(isinstance(c, str) for c in data["commands"]):
        problems.append(f"{agent}: 'commands' must be a list of strings")

    # No evidence file may embed this machine's real username in an absolute path (sprint-1 gate hygiene
    # finding). Checked regardless of status -- NOT_INSTALLED records still carry a real_config_check.path.
    home_leak_fields = []
    if isinstance(data["scratch_dir"], str) and _has_unscrubbed_home_path(data["scratch_dir"]):
        home_leak_fields.append("scratch_dir")
    if any(isinstance(c, str) and _has_unscrubbed_home_path(c) for c in data["commands"]):
        home_leak_fields.append("commands")
    rcc_path = data["real_config_check"].get("path") if isinstance(data["real_config_check"], dict) else None
    if isinstance(rcc_path, str) and _has_unscrubbed_home_path(rcc_path):
        home_leak_fields.append("real_config_check.path")
    if home_leak_fields:
        problems.append(f"{agent}: evidence embeds an absolute home-directory path (contains '/Users/' or "
                        f"'/home/') in {home_leak_fields} -- harness/live/run.py must scrub "
                        "os.path.expanduser('~') to '~' in these fields before writing evidence")

    asserted = data["asserted"]
    missing_asserted = [f for f in ASSERTED_FIELDS if f not in asserted]
    if missing_asserted:
        problems.append(f"{agent}: 'asserted' is missing {missing_asserted}")
    extra_asserted = [f for f in asserted if f not in ASSERTED_FIELDS]
    if extra_asserted:
        problems.append(f"{agent}: 'asserted' has unexpected fields {extra_asserted}")
    non_bool = [f for f in ASSERTED_FIELDS if f in asserted and not isinstance(asserted[f], bool)]
    if non_bool:
        problems.append(f"{agent}: 'asserted' fields must be booleans: {non_bool}")

    real_config_check = data["real_config_check"]
    missing_rcc = [f for f in REAL_CONFIG_CHECK_FIELDS if f not in real_config_check]
    if missing_rcc:
        problems.append(f"{agent}: 'real_config_check' is missing {missing_rcc}")
    extra_rcc = [f for f in real_config_check if f not in REAL_CONFIG_CHECK_FIELDS]
    if extra_rcc:
        problems.append(f"{agent}: 'real_config_check' has unexpected fields {extra_rcc}")
    bad_rcc_type = [f for f, kind in REAL_CONFIG_CHECK_FIELDS.items()
                     if f in real_config_check and not isinstance(real_config_check[f], kind)]
    if bad_rcc_type:
        problems.append(f"{agent}: 'real_config_check' fields have the wrong type: {bad_rcc_type}")

    if missing_asserted or non_bool:
        return problems   # the invariants below need all three flags to exist and be booleans

    all_true = all(asserted[f] for f in ASSERTED_FIELDS)
    all_false = all(not asserted[f] for f in ASSERTED_FIELDS)
    if data["status"] == "VERIFIED_LIVE":
        if not (data["log_records"] > 0 and all_true):
            problems.append(f"{agent}: status is VERIFIED_LIVE but log_records={data['log_records']} and "
                            f"asserted={asserted} do not both satisfy log_records > 0 and all flags true")
        # A VERIFIED_LIVE claim must be backed by the commands and scratch project that a real run always
        # produces -- this is exactly the fabrication shape found by editing a copy of an evidence file to
        # claim VERIFIED_LIVE with log_records>0 and every asserted flag true but commands=[] and
        # scratch_dir=null: before this check, nothing here caught it.
        if not data["commands"]:
            problems.append(f"{agent}: status is VERIFIED_LIVE but 'commands' is empty -- a real run always "
                            "executes at least the --version probe and the headless agent invocation")
        if data["scratch_dir"] is None:
            problems.append(f"{agent}: status is VERIFIED_LIVE but 'scratch_dir' is null -- a real run "
                            "always creates a scratch project")
        binary_names = ra_init.BINARIES.get(agent, ())
        if (data["commands"] and binary_names
                and not any(name in cmd for cmd in data["commands"] for name in binary_names)):
            problems.append(f"{agent}: status is VERIFIED_LIVE but none of 'commands' names the agent's own "
                            f"binary {binary_names!r}")
    if data["status"] == "NOT_INSTALLED" and not (data["log_records"] == 0 and all_false):
        problems.append(f"{agent}: status is NOT_INSTALLED but log_records={data['log_records']} and "
                        f"asserted={asserted} are not both zero/false -- nothing should have run")
    return problems


def _agent_key_from_path(path: Path) -> str:
    """The expected agent key for an evidence file passed on the command line: its filename stem (e.g.
    "claude.json" -> "claude", regardless of what directory it lives in). `validate_one` then checks the
    file's own "agent" field against this, so a file renamed or copied to disagree with its contents is still
    caught, exactly as it is for the hardcoded EVIDENCE_DIR list below."""
    return path.stem


def main(argv: list[str] | None = None) -> int:
    """With explicit paths (`argv`, or `sys.argv[1:]` when `argv` is None and this runs as a script):
    validate exactly those files, deriving each one's expected agent key from its filename stem. This is
    what lets `validate.py <path> [<path> ...]` -- including a shell-expanded
    `harness/live/evidence/*.json`, a scratch copy, or a path that does not exist -- actually check the
    files named, instead of silently ignoring them and re-checking the hardcoded default list.

    With no paths at all (`argv == []` and no CLI arguments either): fall back to the hardcoded
    AGENT_KEYS x EVIDENCE_DIR list, same as every call site before this function took arguments."""
    args = sys.argv[1:] if argv is None else argv
    if args:
        pairs = [(_agent_key_from_path(Path(a)), Path(a)) for a in args]
    else:
        pairs = [(agent, EVIDENCE_DIR / f"{agent}.json") for agent in AGENT_KEYS]

    problems: list[str] = []
    for agent, path in pairs:
        problems += validate_one(agent, path)
    if problems:
        for p in problems:
            print(f"VIOLATION: {p}")
        print(f"{len(problems)} violation(s) across {len(pairs)} agent evidence files")
        return 1
    print(f"OK: {len(pairs)} agent evidence files all valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
