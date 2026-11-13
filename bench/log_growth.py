"""Log growth from one big tool input, measured through the real hook process.

One 10 MB Write (Claude Code, file named in the input, checkpointed directly) and one 10 MB Create (Droid, an
agent whose calls are scanned): a pre and a post event each, then the size of .rewindagents/log.jsonl and of
the stored copies. Prints JSON. Stdlib only.

    python3 bench/log_growth.py [--mb 10]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def hook(agent: str, payload: dict, cwd: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", agent],
                   input=json.dumps(payload).encode("utf-8"), capture_output=True, cwd=cwd, env=env,
                   timeout=300, check=True)


def du(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def one(agent: str, pre: str, post: str, tool: str, mb: int) -> dict:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d).resolve()
        target = root / "big.txt"
        target.write_text("old\n", encoding="utf-8")
        content = "x" * (mb * 1024 * 1024)
        base = {"session_id": "s1", "cwd": str(root), "tool_name": tool,
                "tool_input": {"file_path": str(target), "content": content}}
        hook(agent, {**base, "hook_event_name": pre}, root)
        target.write_text(content, encoding="utf-8")             # what the tool did
        hook(agent, {**base, "hook_event_name": post, "tool_response": {"success": True}}, root)
        store = root / ".rewindagents"
        return {"agent": agent, "tool": tool, "input_chars": len(content),
                "log_bytes": (store / "log.jsonl").stat().st_size, "objects_bytes": du(store / "objects")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=int, default=10)
    a = ap.parse_args(argv)
    rows = [one("claude", "PreToolUse", "PostToolUse", "Write", a.mb),
            one("droid", "PreToolUse", "PostToolUse", "Create", a.mb)]
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
