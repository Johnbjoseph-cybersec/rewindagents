#!/usr/bin/env python3
"""Stand-in for `claude -p` used only by `study.py run --dry-run`: tests the runner, costs nothing.

It sleeps a little, then (with probability 0.6) lays the task's reference solution over the working directory,
and prints a Claude-Code-shaped JSON result. It never calls any model.
"""
import json
import random
import shutil
import sys
import time
from pathlib import Path

tasks = Path(__file__).resolve().parent / "tasks"
cwd = Path.cwd()
mod = next((p.name for p in cwd.glob("*.py")), None)
time.sleep(random.uniform(0.3, 1.2))
if mod and random.random() < 0.6:
    for t in tasks.iterdir():
        ref = t / "reference" / mod
        if ref.is_file():
            shutil.copy(ref, cwd / mod)
if "STUB_INFRA" in " ".join(sys.argv) or (Path(__file__).parent / "stub_infra_once").exists():
    flag = Path(__file__).parent / "stub_infra_once"
    flag.unlink(missing_ok=True)
    print(json.dumps({"is_error": True, "subtype": "error", "result": "API Error: 429 rate limit", "num_turns": 0}))
    sys.exit(1)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 900, "num_turns": 3,
                  "total_cost_usd": 0.01, "usage": {"input_tokens": 1, "output_tokens": 1},
                  "modelUsage": {"stub": {}}, "result": "done"}))
