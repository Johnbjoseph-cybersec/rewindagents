# First run, 2026-11-13 (branch worktree-agent-a9dac934443c1e3b9, on top of 31d538c)

Setup: a fresh venv (`python3 -m venv venv && venv/bin/pip install <this branch>`), Python 3.15.0, macOS. A
scratch git project with two files (`calc.py`, `config.ini`), one commit. Agent sessions were driven through
the exact hook command `install` wrote into `.claude/settings.json` (a shell process per hook event, Claude
Code-shaped payloads with a 36-character UUID session id and `CLAUDE_PROJECT_DIR` set), with the tool's real
effect applied between `PreToolUse` and `PostToolUse`. Session A: Read, Edit `calc.py` (adds `div`), Write
`test_calc.py`, Bash `sed -i` on `config.ini`. Then I (the human) added a `# calculator` line to `calc.py` by
hand. Session B: Edit `calc.py` (guards `div` against 0), Bash `rm test_calc.py && echo 'API_TOKEN=...' > .env`.

Verdict in one line: the recorder and rewind are solid; every friction point below is about **the code that
remains** - which line came from which agent step, what a commit or a PR owes to which session - and the tool
has no answer for any of it.

## What worked (no friction)

| Command | Output (trimmed) |
|---|---|
| `rewindagents --version` | `rewindagents 0.0.7` |
| `rewindagents replay` before any hook | `no log at .rewindagents/log.jsonl, here or in a parent directory` + the next step (`init`, `status`). Exit 2. |
| `rewindagents install` | `installed in .claude/settings.json`; the hook names the venv's Python by absolute path. |
| `rewindagents status` | `claude ok`, then `log ok ... (12 records, last 2026-11-13 15:24:00, chain intact)` |
| `rewindagents sessions` | both sessions, steps, files touched, `(latest)` on B |
| `rewindagents replay --session 7f3` | a 3-character prefix of the UUID is enough (31d538c) |
| `rewindagents replay --step 2 --diff` | `created .env`, `deleted test_calc.py`, then the two diffs |
| `rewindagents rewind 1` / `rewind 2` | restore/delete lines, `this rewind is step 3; undo it with: rewindagents rewind 2 --session 9b8d...` |
| `rewindagents branch 0 --name before-agent` | `previous files kept in git branch rewindagents/before-agent (635b4cbdc32d)`; HEAD untouched |
| `rewindagents export` | `wrote .rewindagents/replay-9b8d....html ... 6 secret values replaced` |
| `rewindagents export --out /nonexistent/x.html` | `rewindagents: Read-only file system: /nonexistent`, exit 1, no traceback (31d538c) |
| `rewindagents bundle --out s.bundle`, then `import` in a fresh clone | session imported, paths moved, `replay` there shows `API_TOKEN=[redacted anthropic key]` |
| `rewindagents gc --dry-run` / `gc` | `would delete 3 stored copies (740 bytes); kept 6 ...` / `deleted 3 ...` |
| `rewindagents ui --no-open` | a one-time 127.0.0.1 link, `Ctrl+C stops it` |

## Friction, in the order I hit it

1. **"Which agent wrote this line?" has no answer.** After two sessions and a hand edit, `calc.py` has 9
   lines from four sources (the original commit, session A step 2, my hand edit, session B step 1). The
   obvious command does not exist:
   ```
   $ rewindagents blame calc.py
   rewindagents: error: argument cmd: invalid choice: 'blame' (choose from 'record', 'verify', ...)
   ```
   Every piece of evidence needed is already on disk (each step's before-copy, in log order), but the only
   way to answer is to run `replay --step N --diff` for every step of every session and work it out by eye.
   `git blame calc.py` says "Not Committed Yet" for all of the agent's lines.

2. **A hand edit between sessions is invisible, and an old session's rewind silently overwrites it.**
   ```
   $ rewindagents diff 0 --session 7f3
   -# calculator                       <- my hand edit, made after session A
   ...
   -    if b == 0:                     <- session B's change
   -        raise ZeroDivisionError('b is 0')
   ```
   `rewind 0 --session 7f3` would remove my line and session B's guard along with session A's work, and
   neither `diff` nor `rewind --dry-run` says that the file changed after the session ended, or by whom.
   The plan is per session; the file's history is not.

3. **Nothing ties a commit to the agent work in it.** I committed nothing new, but there is no command that
   says "the uncommitted change in calc.py is 5 lines from session A step 2, 2 from session B step 1, 1 by
   hand". A reviewer of a pull request built this way sees one author (whoever ran `git commit`). The
   `attach` GitHub Action (README) puts a whole session's replay page on the PR, but a reviewer reading the
   diff still has to map each hunk to a step by hand, and a PR made of three sessions needs three pages.

4. **The terminal shows secrets the export hides.** `replay` printed
   `rm test_calc.py && echo 'API_TOKEN=sk-ant-api03-EXAMPLE...` and
   `replay --step 2 --diff` printed the whole token, while `export` and `bundle` replace it. Terminal output
   gets pasted into issues and chats.

5. **"Undo everything the agents did" is one command per session.** `branch 0 --name before-agent` only
   rewound session B (the latest). Session A's `div` stayed. The branch name I chose reads as "before the
   agent" and is not that.

6. **Exit codes for the same mistake differ.** `rewind 99` -> `step 99 is out of range: session ... has 5
   steps`, exit 1. `replay --step 9` -> `step 9 is out of range (1-5)`, exit 2.

7. **`rewindagents --help` lists 19 subcommands in definition order** (`record`, `verify`, `head`, `show`,
   `hook` first), so the five a new user needs (`init`, `replay`, `diff`, `rewind`, `ui`) are not where the
   eye lands. The description line does name them.

8. **`init` without a terminal prints a dry run and exits 0** (`Dry run: nothing written (no --yes, and no
   terminal to ask on)`). Correct and documented, but a script that runs `rewindagents init` gets exit 0 and
   no hook; `install` was the command that actually wrote one.

## What this says about the product

Items 1-3 are one gap: rewindagents knows, step by step, how every file got to its current bytes, and
throws that knowledge away at the moment it matters most - when the change becomes a commit and someone else
has to review, trust or audit it. That is the starting point of `ux-review/TRANSFORMATION.md`.
