"""Record what `ux-review/try-runs.sh` prints, for the site's fork-and-compare panels.

The script records a session through the real hook, forks step 2, makes a second attempt by hand in the fork,
then runs `compare --check` and `compare --diff`. This runs it against an installed `rewindagents` and writes
everything it printed, unedited, to brand/demo/runs.json, split at the script's own `--- ` headings. The site
quotes lines from that file and never types output; tests/test_runs_demo.py runs the script again and fails if
a quoted line changes.

Usage: python3 brand/demo/runs.py <path to an installed rewindagents command>
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "ux-review", "try-runs.sh")
OUT = os.path.join(ROOT, "brand", "demo", "runs.json")


def run(command):
    """{heading: [lines]} for one run of try-runs.sh with `command` as the rewindagents command."""
    out = subprocess.run(["sh", SCRIPT, command], capture_output=True, text=True, check=True).stdout
    heads = set(re.findall(r'^echo "--- (.*)"$', open(SCRIPT, encoding="utf-8").read(), re.M))
    parts, head = {}, None
    for line in out.rstrip("\n").split("\n"):
        if line.startswith("--- ") and line[4:] in heads:   # a diff's own "--- a/file" line is output
            head = line[4:]
            parts[head] = []
        elif head is not None:
            parts[head].append(line)
    return parts


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: runs.py <installed rewindagents command>")
    cmd = os.path.abspath(sys.argv[1])
    version = subprocess.run([cmd, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    data = {"script": "ux-review/try-runs.sh", "command": "rewindagents (installed)", "version": version,
            "commands": {"fork": "rewindagents fork 2 --name clamp",
                         "compare": 'rewindagents compare --check "python3 test_cart.py"',
                         "diff": "rewindagents compare --diff shop clamp"},
            "output": run(cmd)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    print("wrote %s (%s)" % (OUT, version))


if __name__ == "__main__":
    main()
