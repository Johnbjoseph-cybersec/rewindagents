# Efficiency study, 200 runs: pre-registration (2026-11-14)

Approved by John on 2026-11-14 (the "bigger study" of `bench/EFFICIENCY_PLAN.md`): 10 coding tasks, about 200
`claude -p` runs, about 30 USD. This file is committed **before any agent run of the study**; the commit that
adds it is the pre-registration. Nothing below is changed after a run. If something has to change, the change
is a new commit with the reason, and the results say so.

The question: does a workflow built on rewindagents get a coding agent to a correct result **faster, at the same
quality**? The answer may be no. The study is not designed to reach any number.

## Tasks (fixed now, before any run)

`bench/efficiency/study200/tasks/T01..T10`. Each is a small stdlib-Python repository (one module, its
docstrings carrying the contract, a `tests/` directory) shaped like a SWE-bench-Lite instance:

- `issue.md`: a bug report as a user would file it (the symptom, one example). The agent gets this.
- `repo/tests/`: the repository's visible tests, including one that reproduces the reported example and fails
  on the shipped code. The agent sees and runs these.
- `hidden/test_hidden_fix.py`: the hidden tests. They test the behaviour the reported bug belongs to, as the
  function's docstring states it (edge cases of the same contract), plus behaviour that already worked and
  must keep working. **Every hidden assertion follows from the docstring or the issue**; assertions where the
  docstring is ambiguous were removed before this commit (T07: `"1 h"`, `"1.h"`, `".5h"`; T09: whether a long
  word's first piece may continue the current line). The agent never sees the hidden tests (they live in this
  repository; the agent works in a temporary copy of `repo/` only).
- `part2.md`, `repo/SPEC.md`, `hidden/test_hidden_part2.py`: a second, small feature, used only by the H1 arm.
- `reference/`: a correct solution, never shown to the agent.

`verify_tasks.py` checks, with no agent: the shipped repo fails its visible tests and the hidden fix tests;
repo + reference passes the visible tests, the hidden fix tests and the hidden part-2 tests. 10 of 10 pass on
Python 3.15.2 and on 3.9.6 (the agent's `python3` could be either).

| Task | Issue (symptom) | What the hidden tests add (all stated in the docstring) | My guess, written before any run |
|---|---|---|---|
| T01-semver | pre-release sorts after release | full SemVer 2.0.0 item-11 precedence chain, numeric < alphanumeric, ASCII order, build metadata ignored | easy |
| T02-glob | `**/*.py` misses top-level files | `**` as zero-or-more whole segments in leading, middle, trailing position; `a**b` acts like `*`; `*` never crosses `/` | medium |
| T03-dotenv | `#` inside values cuts them | comment only after whitespace, escapes in double quotes only, single quotes literal, junk after a quote is an error with the line number | hard |
| T04-allocate | a cent goes missing | largest-remainder with earlier-index ties, exact on huge integers, zero weights, negative totals, validation, input not modified | medium |
| T05-intervals | touching intervals not merged | empty intervals dropped, lists/tuples/iterators accepted, input not modified, start > end raises | medium |
| T06-toposort | cycles accepted silently | alphabetical tie-break (Kahn order), implicit nodes, a valid `.cycle` path, self-loops | hard |
| T07-duration | `1h30m` reads as 1h | unit order and uniqueness, `m` vs `ms`, leading minus, error cases | medium |
| T08-ttlcache | expired values served | expiry boundary, `get` does not extend life, expired entries evicted before LRU ones, `len`/`in` count live only, validation | hard |
| T09-widthwrap | CJK overflows the width | widths 0/1/2 incl. combining marks and ZWJ, breaking long words without splitting wide chars, never wider than width | hard |
| T10-querystring | encoded `&` splits a pair | decode after splitting, `+` vs `%2B`, UTF-8 across escapes, malformed `%` kept, invalid UTF-8 raises, blanks and repeats | medium |

Difficulty is a guess. John asked for tasks "a single attempt often fails"; whether these are is an outcome of
the study (the solo arm measures it), not something tuned to.

## Agent and isolation (same as the pilot)

`claude -p` with Claude Code as installed (2.1.294 at the time of writing), `--model claude-opus-5-5` (the model
the pilot reported; pinned so a default change cannot slip in), `--output-format json --setting-sources project
--strict-mcp-config --no-session-persistence --permission-mode acceptEdits --allowedTools Read Edit Write Glob
Grep "Bash(python3 -m unittest:*)" --max-turns 30`, environment without `CLAUDE*` variables. User hooks and MCP
servers are excluded. Every run gets its own temporary copy of the task, a fresh git repository with the
rewindagents hook installed (in **every** arm, so the arms differ only in the workflow); the hook's config and
log are hidden from `git status`. Temporary directories are deleted after each unit is scored.

Prompts (`study.py prompt()`): `fix` = the issue + "Run `python3 -m unittest discover -s tests` to check. Do not
edit the existing tests."; `part2` = part2.md + the same line; `both` = the issue, then part2.md, then the line.

## Workflows

1. **solo**: one agent, one copy, nothing else running from this study. Measures one attempt's time T, its
   visible pass and its hidden pass.
2. **race (K = 3)**: three copies of the same starting state, three agents started at once; the kept attempt is
   the first to exit with its visible tests passing. All three are allowed to finish (so their hidden results
   are known); the cost counts all three in full, which is an upper bound for a race that stops the losers.
3. **H1 resume vs restart**: solo attempt 0 of each task runs as usual (it is also a solo data point). Then a
   wreck fixed in advance: one recorded shell step (`rm -rf tests <module>.py`) through the real hook. Resume =
   `rewindagents rewind 0 --session wreck` and one agent doing part 2 only. Restart = a fresh copy and one agent
   doing the issue and part 2. Both are scored on hidden fix + hidden part 2.

## Schedule (fixed order, so a stop for budget cannot pick which data survive)

Round 1, per task T01..T10: the H1 unit (solo 0, resume, restart = 3 runs), then race 0 (3 runs).
Rounds 2-4, per task: solo r, then race r. Round 5, per task: solo 4.
Per task 5 solo + 4 races + 1 resume + 1 restart = 19 runs; **190 runs** in all. `study.py schedule` prints it.

At most 3 Claude processes at a time (a race), never two units at once.

## Stopping rules and failures

- Hard caps: **200 agent runs** started (including repeated ones) and **40 USD** reported cost. Before each unit
  the runner projects its cost as (median cost per run so far) x (runs in the unit) and stops if the cap would be
  passed. A stop leaves the schedule's tail undone; the results are then labelled PARTIAL.
- Infrastructure errors (no parsable result, or an error whose text names a rate/usage limit or an API
  failure) are not agent failures: the run is logged with `infra_error`, the runner waits 5 minutes and
  repeats the whole unit. Those runs count against both caps and are listed in the results. If infrastructure
  errors persist for more than an hour, the study stops and reports partial results.
- Everything else is the agent's result and counts: a wrong fix, hitting `--max-turns`, editing the tests.
  No run is ever repeated to replace a bad one.
- Every run is appended to `bench/efficiency/runs-200.jsonl` the moment it is scored.

## Metrics

Per run: wall-clock from process start to exit (our clock; `duration_ms` from Claude Code also kept), turns,
`total_cost_usd` and token usage as Claude Code reports them, model, visible pass (the tests in the directory as
the agent left them: what a user's check sees), visible pass of the original visible tests, hidden pass, the
task's SHA-256 and the repository commit. Race runs also: time from race start to exit, slot, winner. H1
resume also: rewind time, rewind exit code, whether the rewind restored the pre-wreck files byte for byte.

## Analysis (`study200/analyze.py`, written and committed now)

- **Primary: time to a kept result.** Sequential = one attempt at a time, retry until the visible tests pass,
  at most 6 attempts. Race = race again if no attempt passes visibly, at most 2 races (the same 6 attempts).
  Per task, both are bootstrap medians over 10,000 sequences resampled from that task's measured runs (fixed
  seeds). Reported with: share of sequences whose kept result passes the hidden tests (never passing = fail),
  and median cost per sequence. Speed ratio per task = sequential median / race median.
- **Pooled:** median and range of the per-task ratios; tasks where the race was faster / slower and an exact
  two-sided sign test; mean hidden pass of the kept result per arm; median cost ratio.
- **Decision rule for a headline "faster at equal quality":** pooled median ratio >= 1.10 AND the race faster on
  at least 9 of 10 tasks (sign test p <= 0.021) AND the race's hidden pass no more than 0.05 below sequential.
  If not met, the headline is "no speed advantage found" for racing, with the numbers.
- **Secondary (oracle):** time to the first attempt that passes the hidden tests, per arm (a user cannot know
  this; it bounds what any selection rule could do).
- **Subgroup (exploratory):** tasks whose solo attempts passed hidden 3 of 5 or fewer.
- **Concurrency slowdown:** median wall of a race attempt / median wall of a solo attempt, per task.
- **H1:** per task resume (rewind + agent) vs restart time, hidden pass and cost; medians with n. Reported with
  the caveat that the ratio is set by where the wreck lands (fixed by the scenario), so it is never a headline
  speed-up of the tool.
- Raw per-task tables of every run (medians with min-max). Runs from repeated units are listed separately.

## A feature only if the numbers justify it

If (and only if) the decision rule is met, the smallest one-command feature for the winning workflow (for
example `rewindagents race`) may be built with fail-before/pass-after tests and the suite green twice. If it
is not met, no feature is built from this study.

## Reproduce

```sh
python3 bench/efficiency/study200/verify_tasks.py          # tasks valid, no agent
python3 bench/efficiency/study200/study.py run --dry-run    # the whole schedule with a stub agent, no cost
python3 bench/efficiency/study200/study.py run              # the real study (costs Claude usage)
python3 bench/efficiency/study200/analyze.py                # tables from the log
```
