# Efficiency track: plan (2026-11-14)

Question from John: can rewindagents make a coding agent reach the same quality of result faster? The
multiplier is whatever is measured. Nothing here is designed to reach a target number; losses are reported.

## Rules

- "Same quality" = the same pass rate on the same **hidden** tests, which the agent never sees. The agent and
  any `--check` see only the visible tests.
- Agent: Claude Code headless (`claude -p`), the version installed on this machine, default model, isolated
  from the user's own setup: `--setting-sources project` (no user hooks), `--strict-mcp-config` (no MCP
  servers), `--no-session-persistence`, `--permission-mode acceptEdits` with Bash limited to
  `python3 -m unittest`. Each run in its own temporary copy of the task.
- Per run we record: task, workflow, wall-clock (`duration_ms` reported by Claude Code, and our own clock),
  `num_turns`, `total_cost_usd` and token usage as Claude Code reports them, visible-check and hidden-test
  pass/fail, the task's SHA-256 and the repository commit. Medians with n; never a best single run.
- No other agent is driven: only Claude Code is installed and logged in here. Other vendors are out of scope.

## Hypotheses, ranked by how mechanically real they are for rewindagents

1. **H2 parallel attempts.** Fork the same starting point K times, run K agents at once, keep the first whose
   `--check` passes. If one attempt passes with probability p and takes time T, sequential retries take about
   T/p to the first pass and the race takes about the fastest passing attempt, at K times the tokens. Real
   for any p; large only when p is well below 1. The cost (K x tokens) is reported next to the time.
2. **H1 resume, don't restart.** When a shell command wrecks the files at step N, `rewindagents rewind` puts
   them back (takeback-bench S01, S02, S05) and the agent continues with only the remaining work; Claude
   Code's `/rewind` does not restore files only Bash changed (its checkpointing docs, Limitations), so the
   documented alternative is git or a restart. The saving is set by where the wreck lands (work before N is
   kept), so the ratio is a property of the scenario, not of the tool: it is reported with that caveat and
   is not a headline number.
3. **H3 hand the next agent the recorded context** (the replay of what was tried). Not measured in the pilot.

## Pilot (approved up to 10 agent runs): 9 runs

Task `cart` (bench/efficiency/tasks/cart): a small stdlib Python module with three seeded bugs, its spec in
docstrings, two visible tests and a hidden test file.

| Runs | Workflow | What it measures |
|---:|---|---|
| 3 | solo: one `claude -p` per fresh copy, one after another | T and p for one attempt |
| 3 | race: three `claude -p` at once, each in its own fork; first to pass the visible check wins | time to first passing attempt, slowdown from running three at once |
| 1 | H1 setup: part 1 (fix the bugs) recorded through the rewindagents hook; then a scripted `rm -rf` wreck | the starting state for H1 |
| 1 | H1 resume: `rewindagents rewind` to before the wreck, then `claude -p` with part 2 only | resume time |
| 1 | H1 restart: fresh copy, `claude -p` with parts 1 and 2 | restart time |

With n = 3 per arm, the pilot can show whether a difference exists and how noisy it is. It cannot support a
published multiplier.

## What a publishable claim needs (needs John's approval: more than 10 runs)

- At least 10 tasks of the SWE-bench-Lite shape (a real bug, hidden tests), chosen before any run, of which a
  fixed share are hard enough that one attempt fails sometimes (p < 0.8 in a calibration run), since that
  is where H2 can matter.
- Per task: 5 solo attempts (calibrates p and T) + 5 races of K = 3 = 20 runs per task; 10 tasks = **200
  runs**. Report per task and pooled: median time to first passing attempt (sequential retries, simulated
  from the solo draws by resampling, and measured races), hidden pass rate of the kept attempt in each arm,
  median tokens and cost per passing result.
- The claim is published only as "on these N tasks, the race reached a passing fix X times faster (median),
  at equal hidden pass rate, using Y times the tokens", with the raw run log.
