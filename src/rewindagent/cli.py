"""rewindagent command line: record, verify, head, show."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rewindagent")
    ap.add_argument("--log", default=".rewindagent/log.jsonl", help="log file (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="append one tool call, read as JSON from stdin")
    r.add_argument("--session", required=True)
    v = sub.add_parser("verify", help="check the hash chain")
    v.add_argument("--head", help="pinned head hash; also catches records cut from the end")
    sub.add_parser("head", help="print the current head hash")
    s = sub.add_parser("show", help="print recorded calls")
    s.add_argument("--session")

    a = ap.parse_args(argv)
    if a.cmd in ("verify", "show") and not Path(a.log).exists():
        print(f"rewindagent: no log at {a.log}", file=sys.stderr)
        return 2
    if a.cmd == "record":
        try:
            call = json.load(sys.stdin)
        except ValueError as e:
            print(f"rewindagent: stdin is not JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(call, dict) or "tool" not in call:
            print("rewindagent: stdin must be an object with a 'tool' key", file=sys.stderr)
            return 2
        rec = log.Recorder(a.log).record(a.session, call["tool"], call.get("args"), call.get("result"),
                                         actor=call.get("actor", "agent"))
        print(rec["hash"])
        return 0
    if a.cmd == "verify":
        ok, n, msg = log.verify(a.log, a.head)
        print(f"{'OK' if ok else 'TAMPERED'}: {n} records, {msg}")
        return 0 if ok else 1
    if a.cmd == "head":
        print(log.head(a.log))
        return 0
    for rec in log.read(a.log, a.session):
        print(f"{rec['seq']:>5}  {rec['session']}  {rec['tool']}  {json.dumps(rec['args'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
