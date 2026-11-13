# Dogfood journal: rewindagents as a new user, 2026-11-14

Setup, exactly as a new user: a fresh venv, `pip install <this worktree>` (the README's `pipx install git+...`
with a local path), `rewindagents init` in small scratch projects, then real Claude Code sessions:
`claude -p` (Claude Code 2.1.294, `--model claude-opus-5-5`, `--setting-sources project --strict-mcp-config`
so only the project's hook runs, as in `bench/efficiency/pilot.py`, `--permission-mode acceptEdits`, tools
Read/Edit/Write/Glob/Grep/Bash/Task). Six real agent runs, USD 0.93 in total (0.109, 0.172, 0.216, 0.305,
0.066, 0.060 as reported by `claude -p --output-format json`; the sixth checked the F11 fix). Hook latency was measured with real hook processes
(`python -m rewindagents hook` fed Claude Code shaped payloads), not with an agent.

Projects: `p1` a git repo with a small todo CLI and tests (sessions: add a feature; a refactor with `sed -i`
and `rm -rf tests`; a 15-step feature + README), `p2` a folder that is not a git repo (a session that runs a
subagent with the Task tool, then `rm`s a file), `p3` a git repo whose hook's venv was deleted, `big` a repo
with 15,000 tracked files plus 5,000 git-ignored ones, then 21,001 files, `dl` a non-git folder with 30 files
of 10 MB.

## What worked (keep it)

- Install: 3 s into a fresh venv; `rewindagents --version` printed `rewindagents 0.0.7`.
- The bad run was fully recoverable. After the agent ran `rm -rf tests && sed -i ...`:
  `rewindagents rewind 2 --only tests` -> `restore tests/test_todo.py`, tests passed again, and it printed
  `this rewind is step 4; undo it with: rewindagents rewind 3 --session 0cf8d818-...`.
- `replay --step 3 --diff` showed exactly what step 3 did: `deleted tests/test_todo.py` and the one-line
  `DB` change, as a unified diff.
- A hand edit after the agent was protected: `rewindagents rewind 0` refused, exit 1, named `README.md:
  changed outside any recorded step`, and printed the two ways forward (`diff 0 --session ...`, `--force`).
- Live subagent recording: in `p2` Claude Code's subagent made steps 2-9 (Bash, 3 Reads, 3 Edits, Grep); all
  are in the log, and the 3 Edits are checkpointed. This is the first live subagent session recorded.
- A folder that is not a git repo recorded and rewound the same way.
- A stale hook (venv deleted) was caught: `status` printed `STALE ... python3.15 no longer exists` and
  `Fix: rewindagents init --yes`, exit 1.
- `--session` takes a prefix (`replay --session 0cf8` worked).

## Frictions, in order of daily-use cost

F1. **`init` writes four agents' config files into the repo, and says nothing about committing them.**
`rewindagents init --yes` in `p1` (I use only Claude Code; `~/.codex/`, `~/.gemini/`, `~/.copilot/` exist):
```
  claude   installed      .claude/settings.json
  codex    installed      .codex/hooks.json
  gemini   installed      .gemini/settings.json
  copilot  installed      .github/hooks/rewindagents.json
```
`git status --short` then showed `?? .claude/ ?? .codex/ ?? .gemini/ ?? .github/`. Every one holds an absolute
path to this machine's Python (`/private/tmp/.../venv/bin/python3.15 -m rewindagents hook`): commit them and a
teammate's agent runs a hook that does not exist on their machine. In the third session the agent itself ran
`ls .claude .codex .gemini .github` to find out what they were. There is no way to pick only the agent you use.

F2. **No one-command undo of `init`.** `init` wrote four files; `uninstall` removes one agent at a time and
defaults to Claude Code (`rewindagents uninstall -h`: `--agent {claude,...} (default: claude)`).

F3. **`replay 2` fails although the help says "list a session's steps, or show one step in full".**
```
$ rewindagents replay 2
rewindagents: error: unrecognized arguments: 2
```
(exit 2). It is `replay --step 2`, while `diff 2`, `rewind 2` and `revert 2` all take the step positionally.

F4. **No short answer to "what did the agent just do?".** `replay` lists tool calls (15 lines for the feature
session, Reads included) with `[1 checkpointed]` marks; which files were created, changed or deleted, and by
how many lines, takes `replay --step N --diff` once per step. After the destructive session I had to read three
step diffs to learn "it deleted tests/test_todo.py and changed src/todo.py".

F5. **Python bytecode noise everywhere.** In the git repo without a `__pycache__` ignore line, every Bash step
that ran Python reported `.pyc` files: `replay` `[4 checkpointed]` where 2 were `.pyc`, `sessions` listed
`src/__pycache__/todo.cpython-315.pyc`, `revert 3 --dry-run` would `restore` two `.pyc` files, `fork` warned
`tests/__pycache__/test_todo.cpython-315.pyc: changed outside any recorded step`, and `compare` showed
`(+2 binary)`. The non-git walk already skips `__pycache__`; the git path does not.

F6. **Over 20,000 files, shell commands are silently not protected.** In `big` with 21,001 files three Bash
steps were recorded as plain lines:
```
    7  Bash          echo hi
```
and `status` said `log ok ... chain intact`. Nothing tells the user that a `rm` in that project cannot be
rewound (the record holds `bash_scan: {"skipped": "more than 20000 files"}`).

F7. **The store's disk use is invisible.** In `dl` (30 files x 10 MB, not a git repo) one Bash step made
`.rewindagents/` 286 MB (`du -sh`): the before-scan copies every project file under 20 MB. `status` does not
show it; `gc --dry-run` shows only what it would free.

F8. **`status` says "run the hook command by hand" without the command.**
```
A hook is in place but nothing is recorded yet. Run the agent once; if it made a tool call and there is still
no record, the hook is failing: run the hook command by hand to see why.
```

F9. **A stale hook fails silently inside the agent.** In `p3` (hook's venv deleted) `claude -p "Change
app.py ..."` succeeded, nothing was recorded, and Claude Code said nothing (hook errors are not shown in a
normal session). Only `rewindagents status` reveals it.

F11. **A shell command that fails was never checkpointed (found while building the summary).** In `p1`'s
feature session, step 11 was `export TODO_DB=... && python3 src/todo.py add ... ; ls data 2>&1` (exit 1). Its
`replay 11` shows `"checkpoints": []`, and `.rewindagents/pending/2efa2171...json` was still there: the post
event never reached the hook. Claude Code sends a failed call to `PostToolUseFailure` ("After a tool call
fails", code.claude.com/docs/en/hooks, read 2026-11-14), and the hook was installed on `PostToolUse` only. So
`rm notes.txt && ... && ls does-not-exist` lost `notes.txt` for good; agents run failing commands (a red test
run) all the time. After the fix, the same real command in `p4`:
```
$ rewindagents summary
Session e43ef0ba (claude, 2026-11-14 04:15:09 to 04:15:10): 1 step, 1 shell command.
2 files different now from before its first step:
  deleted  notes.txt  -1           step 1
  changed  data.txt   +1 -1        step 1
```
and `rewindagents rewind 0` put `notes.txt` back.

F10. **`fork` needs `--name`.** `rewindagents fork 2` -> `error: the following arguments are required:
--name` (exit 2).

## Measured: hook latency (real hook processes, macOS arm64, Python 3.15)

| project | Bash pre | Bash post | Edit pre | Edit post |
|---|---|---|---|---|
| 15,000 tracked + 5,000 ignored files (80 MB) | 381-409 ms (800 ms first call) | 301-341 ms | 54-58 ms | 56-61 ms |
| 21,001 files (over the limit: no scan) | 228-250 ms | 49-53 ms | 52-53 ms | 48-59 ms |
| 30 files x 10 MB, not a git repo | 125-320 ms | 102-133 ms | 113-157 ms | 93-95 ms |

So a shell command in a 15,000-file repo costs about 0.7 s of hook time; an edit about 0.1 s. Acceptable for
daily use, not invisible; documented in the README.

## What was fixed on branch usable/v0.1 (each with a test that fails on the code before it)

| # | friction | status | test |
|---|---|---|---|
| F11 | failing command never checkpointed | fixed: hook installed on `PostToolUseFailure`; checked live in `p4` | `tests/test_recording_gaps.py` |
| F1 | init writes 4 agents' files into the repo | fixed: `init --agent NAME`; created files go to `.git/info/exclude`; a tracked one is named | `tests/test_usable.py` TestInitAgentAndExclude |
| F2 | no undo of init | fixed: `init --undo` (all agents, stale hooks too, keeps history) | TestInitUndo |
| F4 | no "what did it just do" | fixed: `rewindagents summary` (net files, lines, steps, 3 undo commands) | TestSummary |
| F3 | `replay 2` rejected | fixed: positional step | TestReplayStep |
| F5 | `.pyc` noise in git repos | fixed: untracked files under skip dirs are not scanned | `tests/test_recording_gaps.py` |
| F6 | >20,000 files: shell steps silently unprotected | fixed: `replay` marks `[NOT checkpointed: ...]`, `status` warns, `summary` notes | TestNotScannedIsVisible |
| F8, F9 | failing hook invisible; status said "run the hook by hand" | fixed: `status` runs each hook once in a temp dir: `FAILING` + the hook's own error, exit 1; "Recording works" when it does | TestStatus |
| F7 | store size invisible | partly: `status` shows the store's size and points at `gc`; no automatic gc (the store is a copy of the project that the next shell step needs again) | TestStatus |
| F10 | `fork` needs `--name` | not fixed | - |

After the fixes, the quickstart from the built wheel in a fresh venv (`pip install rewindagents-0.0.8-py3-none-any.whl`,
`init --yes --agent claude`, one real `claude -p` run that added a function and then `rm`'d the test file):
`summary` listed `deleted test_calc.py -3 steps 2, 3` and `changed calc.py +4 -0`, `revert 3` brought the test
file back with the agent's new test in it, `python3 test_calc.py` printed `ok`, `init --undo` left `git status`
showing only the agent's own changes. `__pycache__/` was not reported.
