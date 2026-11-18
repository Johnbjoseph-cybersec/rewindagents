"""The five `--json` shapes (sessions, summary, diff, replay, rewind --dry-run), read-only.

Each function here reads the log the same way the matching human command does -- through `rewind.py`,
`diff.py` and `sessions.py`, never by re-reading `.jsonl` lines itself -- so the JSON a script parses
and the text a person reads can never disagree about what happened. Nothing here writes to the log or
the working tree; `rewind_plan_payload` and `revert_result_payload` only describe a plan or a result
that `cli.py` or `mcp.py` already computed (a real write, when there is one, happened in `rewind.py`
or `revert.py` before this module ever sees it).

`cli.py` and `mcp.py` both call these, so the CLI's `--json` output and the MCP server's tool results
are the same shape by construction, not by two authors agreeing to keep them in sync.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from . import diff as diffs
from . import log, redact, rewind, sessions

FORMAT_VERSION = 1


def error_payload(message: str) -> dict:
    """The one shape a hard failure takes on stdout under --json: still exactly one JSON object."""
    return {"format": "rewindagents-error", "version": FORMAT_VERSION, "error": message}


def _iso(ts: float) -> str:
    """Epoch seconds as UTC, millisecond precision, with a Z suffix: no local clock, no offset to parse."""
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def sessions_payload_from(found: list[dict]) -> dict:
    """The shape alone, from a list `sessions.sessions()` already built (so a caller that also needs the
    list for its own exit code, as the CLI's --grep does, does not read the log twice)."""
    return {
        "format": "rewindagents-sessions", "version": FORMAT_VERSION,
        "sessions": [
            {"session": e["session"], "steps": e["steps"], "first_ts": _iso(e["first"]), "last_ts": _iso(e["last"])}
            for e in found
        ],
    }


def sessions_payload(log_path: str | Path, grep: str | None = None) -> dict:
    """`sessions --json` / the `rewind_sessions` MCP tool. `grep` matches the CLI's own --grep."""
    return sessions_payload_from(sessions.sessions(log_path, grep))


def _rows(log_path: str | Path, session: str | None = None) -> tuple[str | None, list[dict]]:
    """(resolved session, one row per step: seq, ts, actor, event, tool, files, result).

    `rewind.steps_from` pairs "pre"/"post" records into steps but keeps neither "ts" nor "actor" (they
    are not part of a step's own identity -- see rewind.py). Every record that is not a "post" starts
    exactly one step, in the same order it is read, so zipping the non-post records with the steps
    `steps_from` built from the very same list recovers them without re-deriving any pairing logic of
    rewind.py's own.
    """
    session = session or rewind.latest_session(log_path)
    recs = log.read(log_path, session)
    steps = rewind.steps_from(recs)
    meta = [r for r in recs if r.get("event") != "post"]
    root = rewind.project_root(log_path)
    rows = []
    for r, s in zip(meta, steps):
        files = list(dict.fromkeys(rewind.relative(cp["path"], root) for cp in s["checkpoints"]))
        rows.append({"seq": s["seq"], "ts": r["ts"], "actor": r.get("actor") or "agent", "event": s["event"],
                     "tool": s["tool"], "files": files, "result": s["result"]})
    return session, rows


def summary_payload(log_path: str | Path, session: str | None = None) -> dict:
    """`summary --json` / the `rewind_summary` MCP tool: every step of a session, and what it touched."""
    session, rows = _rows(log_path, session)
    return {
        "format": "rewindagents-summary", "version": FORMAT_VERSION, "session": session,
        "steps": [{"seq": r["seq"], "ts": _iso(r["ts"]), "actor": r["actor"], "event": r["event"],
                   "tool": r["tool"], "files": r["files"]} for r in rows],
    }


def replay_payload(log_path: str | Path, session: str | None = None, step: int | None = None,
                   from_seq: int | None = None, to_seq: int | None = None, redact_secrets: bool = True) -> dict:
    """`replay --json` / the `rewind_replay` MCP tool: the same step rows as `summary_payload`, plus each
    step's own result. `step` (the CLI's `replay N` / `--step N`) selects one step by position; the MCP
    tool instead takes an optional [from_seq, to_seq] range over the log's own sequence numbers -- the
    two never apply together. With neither, every step of the session is listed, as plain `replay` does.
    Secrets in a step's result are replaced by default (redact_secrets=True), as every other surface
    that may print a result to a screen or a chat transcript already does (replay, export, bundle)."""
    session, rows = _rows(log_path, session)
    if step is not None:
        if not 1 <= step <= len(rows):
            raise rewind.StepRangeError(rewind.range_message(step, session, len(rows), 1))
        rows = [rows[step - 1]]
    elif from_seq is not None or to_seq is not None:
        rows = [r for r in rows if (from_seq is None or r["seq"] >= from_seq)
                and (to_seq is None or r["seq"] <= to_seq)]
    steps_out = []
    for r in rows:
        result = r["result"]
        if redact_secrets:
            result, _ = redact.value(result)
        steps_out.append({"seq": r["seq"], "ts": _iso(r["ts"]), "actor": r["actor"], "event": r["event"],
                          "tool": r["tool"], "files": r["files"],
                          "result": json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)})
    return {"format": "rewindagents-replay", "version": FORMAT_VERSION, "session": session, "steps": steps_out}


def diff_payload(log_path: str | Path, step: int, session: str | None = None,
                 paths: list[str] | None = None, redact_secrets: bool = False) -> tuple[dict, dict]:
    """`diff --json` / the `rewind_diff` MCP tool: (the JSON shape, the full plan `diffs.diff` returned).

    The plan is returned too so a caller that needs the exit code (cli.py: CANNOT, drift, an unfinished
    scan) does not have to re-derive "change" from it a second time; diff.py is never edited to add this.

    `redact_secrets` defaults to False, matching the plain `diff` command, which has no `--no-redact`
    flag at all because it has nothing to turn off: a diff on a human's own terminal is not redacted,
    under `--json` or not, and `cli.py`'s `diff --json` never passes this argument -- that CLI default
    is unchanged. The MCP server's `rewind_diff` tool is a different audience (its result is as likely
    to land in another LLM's context as in a log file), so `mcp.py` is the one caller that passes
    `redact_secrets=True` by default, with its own explicit, documented opt-in back to raw text. When
    True here, each file's `unified` text is run through `redact.text` the same way a result already
    is in `replay_payload`."""
    p = diffs.diff(log_path, step, session, paths)
    root = rewind.project_root(log_path)
    restore_paths = {q for q, _ in p["restore"]}
    files = []
    for path_s, text in p["files"]:
        if path_s in restore_paths:
            change = "modified" if Path(path_s).is_file() else "created"
        else:
            change = "deleted"
        if redact_secrets:
            text, _ = redact.text(text)
        files.append({"path": rewind.relative(path_s, root), "change": change, "unified": text})
    payload = {"format": "rewindagents-diff", "version": FORMAT_VERSION, "session": p["session"],
              "step": p["to_step"], "files": files}
    return payload, p


def diff_exit_code(p: dict) -> int:
    """The same exit code `diff` (without --json) already returns for this plan; see diff.run."""
    return 1 if p["cannot"] or p["bash_uncovered"] or p["scan_early"] or p.get("drift") or p.get("torn") else 0


def rewind_plan_payload(p: dict, root: Path) -> dict:
    """The `rewindagents-rewind-plan` shape, from a plan `rewind.rewind` (dry_run=True or not) returned."""
    restores = []
    for path_s, _ in p["restore"]:
        action = "restore" if Path(path_s).is_file() else "create"
        restores.append({"path": rewind.relative(path_s, root), "action": action})
    for path_s in p["delete"]:
        restores.append({"path": rewind.relative(path_s, root), "action": "delete"})
    drift = [{"path": rewind.relative(d["path"], root), "reason": rewind.drift_why(d)} for d in p.get("drift") or []]
    return {"format": "rewindagents-rewind-plan", "version": FORMAT_VERSION, "session": p["session"],
            "to": p["to_step"], "restores": restores, "drift": drift}


def rewind_dry_run_exit_code(p: dict, force: bool) -> int:
    """The same exit code `rewind --dry-run` (without --json) already returns for this plan: 1 when the
    real rewind would refuse (drift, and --force was not given) or could not put everything back
    (CANNOT, an unfinished scan, a torn write), 0 otherwise. See cli.py's non-json rewind/branch dispatch."""
    if p.get("drift") and not force:
        return 1
    return 1 if p["cannot"] or p["bash_uncovered"] or p["scan_early"] or p.get("torn") else 0


def revert_result_payload(p: dict, root: Path) -> dict:
    """Not one of the CLI's five --json shapes (revert has no --json flag); the `rewind_revert_step`
    MCP tool's own result, from the plan `revert.revert` returned after it wrote."""
    return {
        "format": "rewindagents-revert-result", "version": FORMAT_VERSION, "session": p["session"],
        "step": p["step"], "write": [rewind.relative(q, root) for q, _, _ in p["write"]],
        "delete": [rewind.relative(q, root) for q in p["delete"]],
        "same": [rewind.relative(q, root) for q in p["same"]],
        "merged": [rewind.relative(q, root) for q in p["merged"]],
        "cannot": [{"path": rewind.relative(q, root), "why": why} for q, why in p["cannot"]],
        "record": p.get("record"),
    }
