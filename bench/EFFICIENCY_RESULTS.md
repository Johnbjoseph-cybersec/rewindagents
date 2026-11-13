# Efficiency study, 200-run budget: results (2026-11-14)

Pre-registration: `bench/EFFICIENCY_STUDY_PLAN.md`, committed at e7d757c **before** the first agent run; every
run below was made at that commit. Raw log: `bench/efficiency/runs-200.jsonl` (190 lines, one per agent run),
runner output `bench/efficiency/study200/run.log`. The tables are the unedited output of
`python3 bench/efficiency/study200/analyze.py`.

## Headline the data supports

> **No speed advantage found for racing.** On 10 bug-fix tasks (190 real Claude Code runs, claude-opus-5-5),
> racing three agents and keeping the first that passed the visible tests was *slower* than one agent on 9 of
> 10 tasks (median 0.94 times the speed, range 0.86 to 1.02) and cost 3.07 times as much, because a single
> attempt already passed the hidden tests 49 times out of 50.

For the resume arm, the only sentence we can stand behind is about restoring, not speed: after a scripted
`rm -rf` of the tests and the module, `rewindagents rewind` restored the pre-wreck files byte for byte in
10 of 10 tasks (0.05 to 0.13 s), and the agent then finished only the remaining work. Finishing that way took
a median 26.4 s against 48.2 s for a restart from zero (n = 10), but that ratio is set by where the scenario
put the wreck, not by the tool.

## What happened, in plain words

- **The tasks were easier than intended.** I wrote them to include ones "a single attempt often fails". It
  did not: solo attempts passed the hidden tests 49 of 50 times, race attempts 118 of 120. All 4 hidden
  failures in 190 runs were on T03-dotenv (one solo, two race attempts, one restart). The pre-registered
  subgroup "tasks with 3 of 5 solo passes or fewer" is empty, so the case where racing could pay off was not
  present in this study either. That is a finding about Claude Opus 5.5 on small, well-documented bug fixes,
  not about racing on hard tasks.
- **The visible tests never failed** (0 of 190 runs ended with a failing visible check). So "keep the first
  attempt that passes the check" always meant "keep the fastest attempt", and the check gave no information to
  choose with. On T03 the bootstrap shows the race's kept result passing hidden in 1.00 of sequences against
  0.80 for one attempt; that rests on 1 failing solo run out of 5 and 2 failing race attempts that were never
  the first to finish, so it is noise-level and not a quality claim.
- **Why the race lost time:** three Claude Code processes at once made each attempt about 7 % slower (median
  over tasks 1.07, range 1.04 to 1.22) and attempt times varied little (most tasks within about 10 s), so the
  fastest of three did not make up the slowdown. The sign test that the pre-registration uses for a "faster"
  claim came out at p = 0.021 in the *opposite* direction (1 faster, 9 slower).
- **Cost:** the race used 2.87 to 3.27 times the cost of one attempt (all three attempts ran to the end; a race
  that stops the losers would cost somewhat less, which was not measured).

## Claims we must NOT make

- Any speed multiplier for rewindagents (2x, 4x, "1.8x faster"). The 1.82 resume/restart ratio is a property of
  this scenario's wreck point (after part 1 of 2), not of the tool; a wreck later in the job gives a larger
  ratio and an earlier one a smaller one.
- That racing agents is faster, or that it improves quality. Neither was found.
- That rewindagents makes Claude Code faster, or beats Claude Code's own checkpointing (not compared here).
- That these results say anything about hard tasks, other models or other agents (not measured).
- That the resume arm "passed more often" (10/10 vs 9/10 is one run of difference).

## Feature decision

The pre-registered decision rule for building a race feature (median ratio >= 1.10, race faster on >= 9 of 10
tasks, equal hidden pass) was **NOT MET**, so no `rewindagents race` command was built. Building one on these
numbers would be selling a measured slowdown.

What the data does support as a product message is the existing one, now with 10 more real cases: when a
shell command wrecks an agent's files, `rewindagents rewind` puts them back exactly, so the agent continues
instead of starting over.

## Totals

- Agent runs: **190** of the 200 cap (190 scheduled, 0 repeated, 0 infrastructure errors, 0 agent errors;
  the most turns any run used was 16 of 30). Plus the 9 pilot runs reported earlier, not counted here.
- Cost reported by Claude Code (`total_cost_usd`, API list price; the runs used the logged-in account):
  **33.55 USD** of the 40 USD cap. Median 0.175 USD per run.
- Time: 02:36 to 03:45 IST on 2026-11-14, on a machine shared with other work (1-minute load average 10 to 40
  during the runs), at most 3 study processes at once.

## Limitations

- One machine, one evening, one model, one Claude Code version (2.1.294).
- The tasks are small single-module repositories written for this study, SWE-bench-Lite-shaped but not from
  SWE-bench; hidden tests are mine. The agent's file tools were not confined to its directory, and this did
  happen: after the runs, two files were found in the system temp directory, `eff200-checks/check.py` (03:05)
  and `eff200-scratch/check.py` (03:41), both small scripts that call `envfile.parse` on probe strings,
  written by agents on T03 with the Write tool (they could not run them: Bash was limited to
  `python3 -m unittest`). They were deleted. Nothing shows an agent reading the hidden tests, but reads
  outside the directory were not logged, so this cannot be ruled out.
- The sequential and race arms are bootstrap resamples of 5 solo runs and 4 races per task.
- The wall clock includes Claude Code start-up and the rewindagents hook (installed in every arm).

## Tables (output of analyze.py)

Log: `bench/efficiency/runs-200.jsonl`, 190 agent runs in all (190 in complete units, 0 in units repeated after an infrastructure error or a crash), total cost reported by Claude Code 33.55 USD.
Models reported: claude-opus-5-5. Claude Code: 2.1.294 (Claude Code). Commits: e7d757c.
Units complete: 90 of 90.

### Every task, raw (median wall-clock in seconds, min-max in brackets)

| task | solo n | solo visible | solo hidden | solo wall | race attempts n | race attempt hidden | race attempt wall | races | race kept hidden | race time to kept |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T01-semver | 5 | 5/5 | 5/5 | 27.8 [21.8-31.0] | 12 | 12/12 | 29.4 [26.9-30.3] | 4 | 4/4 | 28.7 |
| T02-glob | 5 | 5/5 | 5/5 | 31.8 [29.3-49.0] | 12 | 12/12 | 36.5 [30.8-43.1] | 4 | 4/4 | 36.4 |
| T03-dotenv | 5 | 5/5 | 4/5 | 46.8 [37.2-58.7] | 12 | 10/12 | 48.8 [42.6-59.5] | 4 | 4/4 | 48.8 |
| T04-allocate | 5 | 5/5 | 5/5 | 26.4 [22.7-29.7] | 12 | 12/12 | 28.5 [22.5-32.0] | 4 | 4/4 | 26.4 |
| T05-intervals | 5 | 5/5 | 5/5 | 26.2 [24.6-34.3] | 12 | 12/12 | 30.8 [24.5-35.9] | 4 | 4/4 | 28.3 |
| T06-toposort | 5 | 5/5 | 5/5 | 33.9 [31.3-36.7] | 12 | 12/12 | 35.3 [33.0-36.2] | 4 | 4/4 | 35.3 |
| T07-duration | 5 | 5/5 | 5/5 | 35.0 [29.9-40.7] | 12 | 12/12 | 40.2 [30.0-42.6] | 4 | 4/4 | 34.5 |
| T08-ttlcache | 5 | 5/5 | 5/5 | 35.6 [29.4-39.0] | 12 | 12/12 | 37.7 [32.6-39.9] | 4 | 4/4 | 37.0 |
| T09-widthwrap | 5 | 5/5 | 5/5 | 40.4 [35.4-46.4] | 12 | 12/12 | 49.1 [42.8-62.4] | 4 | 4/4 | 45.4 |
| T10-querystring | 5 | 5/5 | 5/5 | 36.0 [34.5-37.1] | 12 | 12/12 | 37.9 [32.1-41.5] | 4 | 4/4 | 37.3 |

### Primary: time to a kept result, sequential retries vs racing 3 (pre-registered policy)

Sequential: one attempt at a time, retry until the visible tests pass (at most 6 attempts). Race: 3 at once, keep the first to pass the visible tests, race again if none does (at most 2 races). Both are bootstrap medians over 10000 resampled sequences of the measured runs (seed 0). Hidden = share of sequences whose kept result passes the hidden tests (a sequence that never passes counts as a fail). Cost = median USD per sequence; a race counts all three attempts, run to the end.

| task | seq time s | seq hidden | seq cost | race time s | race hidden | race cost | speed ratio (seq/race) | cost ratio (race/seq) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T01-semver | 27.8 | 1.00 | 0.157 | 28.0 | 1.00 | 0.466 | 0.99 | 2.97 |
| T02-glob | 31.8 | 1.00 | 0.170 | 36.2 | 1.00 | 0.511 | 0.88 | 3.01 |
| T03-dotenv | 46.8 | 0.80 | 0.221 | 50.5 | 1.00 | 0.686 | 0.93 | 3.11 |
| T04-allocate | 26.4 | 1.00 | 0.136 | 25.9 | 1.00 | 0.417 | 1.02 | 3.08 |
| T05-intervals | 26.2 | 1.00 | 0.143 | 28.4 | 1.00 | 0.442 | 0.92 | 3.10 |
| T06-toposort | 33.9 | 1.00 | 0.175 | 35.4 | 1.00 | 0.502 | 0.96 | 2.87 |
| T07-duration | 35.0 | 1.00 | 0.177 | 36.3 | 1.00 | 0.543 | 0.96 | 3.07 |
| T08-ttlcache | 35.6 | 1.00 | 0.186 | 39.3 | 1.00 | 0.541 | 0.90 | 2.91 |
| T09-widthwrap | 40.4 | 1.00 | 0.186 | 47.0 | 1.00 | 0.606 | 0.86 | 3.27 |
| T10-querystring | 36.0 | 1.00 | 0.181 | 37.2 | 1.00 | 0.559 | 0.97 | 3.09 |

Pooled over 10 tasks: median speed ratio 0.94 (range 0.86 to 1.02); race faster on 1, slower on 9 (two-sided sign test p = 0.021); mean hidden pass of the kept result: sequential 0.98, race 1.00; median cost ratio 3.07.

Pre-registered decision rule (ratio >= 1.10 AND race faster on >= 9 of 10 tasks AND race hidden pass >= sequential - 0.05): **NOT MET**.

### Secondary: time to the first attempt that passes the HIDDEN tests (oracle: needs knowledge a user does not have)

| task | seq oracle time s | seq reaches hidden pass | race oracle time s | race reaches hidden pass |
|---|---:|---:|---:|---:|
| T01-semver | 27.8 | 1.00 | 28.0 | 1.00 |
| T02-glob | 31.8 | 1.00 | 36.6 | 1.00 |
| T03-dotenv | 52.1 | 1.00 | 47.2 | 1.00 |
| T04-allocate | 26.4 | 1.00 | 25.9 | 1.00 |
| T05-intervals | 26.2 | 1.00 | 28.4 | 1.00 |
| T06-toposort | 33.9 | 1.00 | 35.2 | 1.00 |
| T07-duration | 35.0 | 1.00 | 32.7 | 1.00 |
| T08-ttlcache | 35.6 | 1.00 | 34.7 | 1.00 |
| T09-widthwrap | 40.4 | 1.00 | 45.4 | 1.00 |
| T10-querystring | 36.0 | 1.00 | 37.2 | 1.00 |

Subgroup (exploratory, pre-registered): tasks where solo attempts passed the hidden tests 3 of 5 times or fewer: none.

Concurrency slowdown: per task, median wall of a race attempt / median wall of a solo attempt; median over tasks 1.07 (range 1.04 to 1.22).

### H1: resume after a wreck (rewindagents rewind) vs restart from zero

The wreck is fixed in advance: after part 1 (the issue fix, solo attempt 0), a recorded shell step deletes the tests and the module. Resume = `rewindagents rewind` + an agent doing part 2 only. Restart = a fresh copy and an agent doing parts 1 and 2. Hidden = the hidden fix tests AND the hidden part-2 tests. The ratio is set by how much work lies before the wreck, which the scenario fixes; it is not a property of the tool.

| task | part 1 hidden | restored exactly | rewind s | resume s | resume hidden | resume cost | restart s | restart hidden | restart cost |
|---|---|---|---:|---:|---|---:|---:|---|---:|
| T01-semver | True | True | 0.06 | 35.4 | True | 0.185 | 50.1 | True | 0.264 |
| T02-glob | True | True | 0.05 | 18.6 | True | 0.108 | 47.9 | True | 0.236 |
| T03-dotenv | True | True | 0.06 | 32.4 | True | 0.156 | 67.1 | False | 0.295 |
| T04-allocate | True | True | 0.10 | 14.9 | True | 0.094 | 51.8 | True | 0.248 |
| T05-intervals | True | True | 0.10 | 19.5 | True | 0.099 | 41.7 | True | 0.201 |
| T06-toposort | True | True | 0.10 | 27.4 | True | 0.146 | 44.2 | True | 0.224 |
| T07-duration | True | True | 0.13 | 41.3 | True | 0.188 | 52.9 | True | 0.246 |
| T08-ttlcache | True | True | 0.08 | 25.4 | True | 0.145 | 45.1 | True | 0.232 |
| T09-widthwrap | True | True | 0.08 | 15.8 | True | 0.095 | 48.5 | True | 0.242 |
| T10-querystring | True | True | 0.09 | 32.3 | True | 0.162 | 44.0 | True | 0.215 |

n = 10: median resume 26.4 s vs restart 48.2 s (ratio 1.82); hidden pass resume 10/10, restart 9/10; median cost 0.145 vs 0.239 USD.

### Runs not in the tables above (repeated units)

None.
