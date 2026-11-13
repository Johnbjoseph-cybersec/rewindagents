# takeback-bench

Does an undo tool put back exactly what a coding agent changed, without destroying the work around it?

Agent-capability benchmarks (SWE-bench, Terminal-Bench, Recovery-Bench, UndoBench) score the agent. This one
holds the agent fixed and scores the undo: the same scripted session runs once per tool, then the tool's own
undo recipe runs, and every file is compared by SHA-256 (plus executable bit and symlink target) with the state
the goal asks for. A search on 2026-11-14 found no public benchmark of this kind; `../RESULTS.md` lists the
sources and the results.

```sh
python3 bench/takeback/takeback.py                         # all scenarios x all tools, prints the tables
python3 bench/takeback/takeback.py --write                 # and saves bench/takeback/results.json
python3 bench/takeback/takeback.py --markdown              # re-render bench/RESULTS.md from the saved files
python3 bench/takeback/takeback.py --scenario S06 --tool rewindagents -v
```

Stdlib only, no network, no account, about 20 seconds; each scenario runs in its own temporary directory,
removed after. Needs `git` and `sh` on `PATH`.

## What one scenario is

- a small project: `app.py`, `config.yaml`, `tests/`, an executable `scripts/run.sh`, a binary `logo.png`, a
  git-ignored `.env`, and a file `../outside/notes.txt` next to the project; some scenarios add a 20 MB+ file,
  a symlink, uncommitted work, or no git repository at all;
- a session: agent tool calls (`Write`, `Edit`, and `Bash` commands that really run through `sh -c`) and, in
  S09, an edit by hand that no tool sees;
- a goal: `to K` (files as right after agent step K, keeping later hand edits) or `only K` (undo agent step K
  alone, keep everything after it).

The expected state is not typed in: the harness snapshots every file after every step and derives it. Where the
agent and a person both changed one file after step K, the scenario states the merged bytes.

## Scores

- **exact**: every file under the project and `../outside/` matches the expected state;
- **missed**: a file the goal says should change back and did not;
- **destroyed**: a file the goal says to leave alone that the undo changed (later work lost);
- **silent**: the undo exited 0 although it missed or destroyed something, so the user was not told;
- undo time and the time the tool added during the session, wall-clock, one run each.

## Tools and their fixed recipes

| Tool | During the session | Undo to step K | Undo only step K |
|---|---|---|---|
| rewindagents | `python -m rewindagents hook`, one process per PreToolUse/PostToolUse event, Claude Code's payload | `rewindagents rewind K` | `rewindagents rewind K-1 --only <files step K changed>` (the files `replay --step K` names) |
| git commit per step | `git add -A && git commit` before the session and after every agent step (aider auto-commits its own edits; this also commits after shell commands) | `git reset --hard <commit K>`, then git's clean with `-fd` | `git revert --no-edit <commit K>` |
| git stash snapshot | `git stash push --include-untracked && git stash apply` before the session | `git reset --hard`, git's clean with `-fd`, `git stash apply` (back to the session start) | same |

Claude Code's checkpointing is not driven here (it would need a live, paid session per scenario); its documented
behaviour per scenario is in `../RESULTS.md`, in a separate table, never mixed with measured numbers.

Adding a tool: subclass `Tool` in `takeback.py` (`start`, `before`, `after`, `undo`) and add it to `TOOLS`.
