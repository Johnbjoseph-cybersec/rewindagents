# Results: takeback-bench (restore) and the efficiency pilot

Date 2026-11-14. Everything under "Measured" was produced by the scripts named next to it on this machine;
everything under "Documented, not measured" comes from a vendor's own documentation, quoted, and is never
counted with the measured numbers.

## The headline these numbers support

> On takeback-bench's 15 destructive-agent scenarios, rewindagents put back the exact bytes in 11 and
> destroyed later work in none. Per-step git commits got 11 of the 14 they could run (one needs a git
> repository) and destroyed later work once; a stash snapshot got 1 of 14 and destroyed later work in 12.
> rewindagents was the only one of the three to bring back a deleted git-ignored `.env` and to work without
> a git repository; git won on a symlink and on a file over 20 MB.

What they do **not** support, and must not be said: that rewindagents "broke a benchmark record" (this is a
new benchmark we wrote; there is no record), that it beats git overall (it ties on exact restores and wins
or loses on different scenarios), that it beats Claude Code's checkpointing (not measured; see the documented
table), or any speed multiplier for agents (the efficiency pilot below found none near 4x).

A fair one-liner: "We published an open benchmark for undoing what a coding agent did. rewindagents
restored 11 of 15 scenarios exactly and never destroyed later work; here is every scenario, including the
four it misses."

## Is there an existing benchmark? (searched 2026-11-14)

None that scores an undo/checkpoint *tool* on restoring a coding agent's file changes:

- **UndoBench** (Sah et al., [arXiv 2610.05622](https://arxiv.org/abs/2610.05622v1), summarised by
  [agentpatterns.ai](https://agentpatterns.ai/verification/recovery-as-separate-eval-axis/)) injects one fault
  into enterprise workflows and scores whether the *agent* recovers. The name is taken, so ours is called
  takeback-bench.
- **Recovery-Bench** ([Letta, 2025](https://www.letta.com/blog/recovery-bench)) measures "how well agents can
  recover from errors and corrupted states": the agent model, not a restore tool.
- **RecoverIQ** ([GitHub](https://github.com/sanghamitrajohri/recoveriq)) checks restores against a SHA-256
  manifest, but of its own checkpoint manager inside a cost-per-success study; no plug-in for an outside
  tool, no licence shown.
- **Recoverability as a System Primitive** ([arXiv 2609.13672](https://arxiv.org/html/2609.13672v1)) uses
  "exact restoration (digest match)" as one metric, on document tasks; its code is in "a private versioned
  release candidate".
- **AgentRewind / MettleBench** ([arXiv 2608.14380](https://arxiv.org/abs/2608.14380)) and **Crab**
  ([arXiv 2604.28138](https://arxiv.org/abs/2604.28138)) evaluate recovery runtimes on task success; no
  benchmark of external undo tools is released.
- **vc-bench** (GitButler, [write-up](https://braindetox.kr/en/posts/vcbench_version_control_benchmark_agents.html))
  scores agents editing git history, not restoring files.

The digest-match idea is not new (RecoverIQ, the recoverability paper); a runnable, tool-neutral set of
coding-agent wreck scenarios with a derived oracle and a "destroyed later work" score is what is new here.

## Method

`bench/takeback/README.md` has the details. In short: each scenario builds a small project, runs a scripted
session (Write/Edit calls and real `sh -c` commands; one hand edit in S09), snapshots every file after every
step, derives the expected state from those snapshots, runs the tool's fixed undo recipe, and compares every
file under the project and one directory beside it by SHA-256, executable bit and symlink target.
rewindagents is driven through `python -m rewindagents hook`, one process per event, with Claude Code's
payload, exactly as an agent runs it. One run per cell; times are wall-clock on a machine shared with other
work (load average 30 to 45 during the runs), so they show order of magnitude only.

Reproduce:

```sh
cd <a clone of this repository, on branch bench/undo-bench>
python3 bench/takeback/takeback.py            # about 20 s, prints both tables
git checkout 6e08a05 -- src && python3 bench/takeback/takeback.py && git checkout HEAD -- src   # the baseline
```

## Measured: current code (branch, after the two fixes)

<!-- takeback:current:start -->
Measured on macOS 27.0.1, arm64, 12 CPUs, Python 3.15.2, git version 2.50.1 (Apple Git-155), on 2026-11-14 at commit de05532.

| Scenario | rewindagents | git commit per step | git stash snapshot |
|---|---|---|---|
| S01 Bash `rm -rf tests` deletes the test suite | exact | exact | DESTROYED app.py (exit 0: silent) |
| S02 Bash `sed -i` rewrites config.yaml | exact | exact | DESTROYED app.py (exit 0: silent) |
| S03 Write tool overwrites app.py with a stub | exact | exact | DESTROYED README.md (exit 0: silent) |
| S04 agent creates helper.py (never committed), then breaks it | exact | exact | missed helper.py (exit 0: silent) |
| S05 Bash overwrites a binary file (logo.png) | exact | exact | DESTROYED app.py (exit 0: silent) |
| S06 Bash `rm .env` deletes a git-ignored file | exact | missed .env (exit 0: silent) | DESTROYED app.py; missed .env (exit 0: silent) |
| S07 Bash truncates a tracked file over 20 MB | refused; missed data/fixtures.bin (exit 1) | exact | DESTROYED app.py (exit 0: silent) |
| S08 Bash appends to a file outside the project (../outside/notes.txt) | missed ../outside/notes.txt (exit 0: silent) | missed ../outside/notes.txt (exit 0: silent) | DESTROYED app.py; missed ../outside/notes.txt (exit 0: silent) |
| S09 bad Edit to config.yaml, then the user edits the same file by hand | refused; missed config.yaml (exit 1) | DESTROYED config.yaml; missed config.yaml (exit 0: silent) | DESTROYED app.py, config.yaml; missed config.yaml (exit 0: silent) |
| S10 undo only the bad step (`rm -rf tests`), keep the agent's later work | exact | exact | DESTROYED CHANGELOG.md, app.py (exit 0: silent) |
| S11 Bash `rm -rf scripts` deletes an executable script | exact | exact | DESTROYED app.py (exit 0: silent) |
| S12 Bash `rm` deletes a symlink in the project | missed config.local.yaml (exit 0: silent) | exact | DESTROYED app.py (exit 0: silent) |
| S13 project is not a git repository; Bash `rm -rf tests` | exact | n/a (needs a git repository) | n/a (needs a git repository) |
| S14 five-step session (Write, Edit, mv, sed -i, new file), back to step 2 | exact | exact | DESTROYED pricing.py; missed app.py (exit 0: silent) |
| S15 undo the whole session over uncommitted work from before it | exact | exact | exact |
| **exact, of scenarios run** | **11 / 15** | **11 / 14** (1 n/a) | **1 / 14** (1 n/a) |
| **runs that destroyed later work** | 0 | 1 | 12 |

Undo time / time the tool added while the session ran (one run each, wall-clock):

| Scenario | rewindagents undo / record | git commit per step undo / record | git stash snapshot undo / record |
|---|---|---|---|
| S01 | 64 / 350 ms | 31 / 188 ms | 38 / 50 ms |
| S02 | 69 / 303 ms | 45 / 249 ms | 44 / 79 ms |
| S03 | 63 / 257 ms | 36 / 233 ms | 37 / 56 ms |
| S04 | 58 / 281 ms | 31 / 193 ms | 45 / 56 ms |
| S05 | 69 / 299 ms | 46 / 181 ms | 35 / 47 ms |
| S06 | 59 / 394 ms | 37 / 196 ms | 36 / 52 ms |
| S07 | 56 / 345 ms | 55 / 359 ms | 56 / 89 ms |
| S08 | 66 / 323 ms | 39 / 220 ms | 51 / 81 ms |
| S09 | 53 / 262 ms | 40 / 204 ms | 51 / 68 ms |
| S10 | 70 / 530 ms | 23 / 238 ms | 37 / 49 ms |
| S11 | 74 / 313 ms | 34 / 194 ms | 48 / 58 ms |
| S12 | 75 / 334 ms | 32 / 171 ms | 47 / 53 ms |
| S13 | 68 / 297 ms | n/a | n/a |
| S14 | 67 / 784 ms | 42 / 412 ms | 35 / 53 ms |
| S15 | 65 / 310 ms | 38 / 179 ms | 71 / 119 ms |
<!-- takeback:current:end -->

## Measured: baseline (before this branch's fixes)

<!-- takeback:baseline:start -->
Measured on macOS 27.0.1, arm64, 12 CPUs, Python 3.15.2, git version 2.50.1 (Apple Git-155), on 2026-11-14 at commit 6e08a05.

| Scenario | rewindagents | git commit per step | git stash snapshot |
|---|---|---|---|
| S01 Bash `rm -rf tests` deletes the test suite | exact | exact | DESTROYED app.py (exit 0: silent) |
| S02 Bash `sed -i` rewrites config.yaml | exact | exact | DESTROYED app.py (exit 0: silent) |
| S03 Write tool overwrites app.py with a stub | exact | exact | DESTROYED README.md (exit 0: silent) |
| S04 agent creates helper.py (never committed), then breaks it | exact | exact | missed helper.py (exit 0: silent) |
| S05 Bash overwrites a binary file (logo.png) | exact | exact | DESTROYED app.py (exit 0: silent) |
| S06 Bash `rm .env` deletes a git-ignored file | missed .env (exit 0: silent) | missed .env (exit 0: silent) | DESTROYED app.py; missed .env (exit 0: silent) |
| S07 Bash truncates a tracked file over 20 MB | refused; missed data/fixtures.bin (exit 1) | exact | DESTROYED app.py (exit 0: silent) |
| S08 Bash appends to a file outside the project (../outside/notes.txt) | missed ../outside/notes.txt (exit 0: silent) | missed ../outside/notes.txt (exit 0: silent) | DESTROYED app.py; missed ../outside/notes.txt (exit 0: silent) |
| S09 bad Edit to config.yaml, then the user edits the same file by hand | refused; missed config.yaml (exit 1) | DESTROYED config.yaml; missed config.yaml (exit 0: silent) | DESTROYED app.py, config.yaml; missed config.yaml (exit 0: silent) |
| S10 undo only the bad step (`rm -rf tests`), keep the agent's later work | exact | exact | DESTROYED CHANGELOG.md, app.py (exit 0: silent) |
| S11 Bash `rm -rf scripts` deletes an executable script | missed scripts/run.sh (bytes back, +x lost) (exit 0: silent) | exact | DESTROYED app.py (exit 0: silent) |
| S12 Bash `rm` deletes a symlink in the project | missed config.local.yaml (exit 0: silent) | exact | DESTROYED app.py (exit 0: silent) |
| S13 project is not a git repository; Bash `rm -rf tests` | exact | n/a (needs a git repository) | n/a (needs a git repository) |
| S14 five-step session (Write, Edit, mv, sed -i, new file), back to step 2 | exact | exact | DESTROYED pricing.py; missed app.py (exit 0: silent) |
| S15 undo the whole session over uncommitted work from before it | exact | exact | exact |
| **exact, of scenarios run** | **9 / 15** | **11 / 14** (1 n/a) | **1 / 14** (1 n/a) |
| **runs that destroyed later work** | 0 | 1 | 12 |

Undo time / time the tool added while the session ran (one run each, wall-clock):

| Scenario | rewindagents undo / record | git commit per step undo / record | git stash snapshot undo / record |
|---|---|---|---|
| S01 | 81 / 303 ms | 42 / 215 ms | 37 / 47 ms |
| S02 | 64 / 333 ms | 34 / 186 ms | 36 / 48 ms |
| S03 | 78 / 261 ms | 37 / 182 ms | 45 / 56 ms |
| S04 | 69 / 276 ms | 40 / 203 ms | 37 / 51 ms |
| S05 | 66 / 333 ms | 36 / 170 ms | 36 / 56 ms |
| S06 | 65 / 294 ms | 34 / 170 ms | 35 / 46 ms |
| S07 | 63 / 315 ms | 57 / 171 ms | 63 / 90 ms |
| S08 | 72 / 342 ms | 35 / 176 ms | 37 / 47 ms |
| S09 | 70 / 283 ms | 42 / 212 ms | 40 / 52 ms |
| S10 | 70 / 453 ms | 22 / 226 ms | 36 / 53 ms |
| S11 | 66 / 311 ms | 35 / 174 ms | 35 / 47 ms |
| S12 | 67 / 307 ms | 43 / 191 ms | 36 / 47 ms |
| S13 | 68 / 320 ms | n/a | n/a |
| S14 | 67 / 752 ms | 37 / 352 ms | 33 / 59 ms |
| S15 | 82 / 298 ms | 35 / 181 ms | 72 / 136 ms |
<!-- takeback:baseline:end -->

## Documented, not measured: Claude Code checkpointing

Claude Code's checkpointing was not driven by the bench (each cell would need a live, paid session). What its
documentation ([code.claude.com/docs/en/checkpointing](https://code.claude.com/docs/en/checkpointing), read
2026-11-14) says it would do per scenario:

- (a) "Claude Code tracks all changes made by its file editing tools"; "Every prompt you send that starts a
  turn creates a new checkpoint" (so a restore goes back to the start of a prompt, not to one tool call).
- (b) "A file that only Bash commands changed isn't tracked and stays as it is." But "Once Claude has edited
  a file with its file editing tools in your conversation, `/rewind` undoes changes that Bash commands make to
  that file afterward."
- (c) "Checkpointing doesn't rewind symlinked or hard-linked files."
- (d) "Manual changes you make to files outside of Claude Code ... are normally not captured, unless they
  happen to modify the same files as the current session."

| Scenario | Documented behaviour | Rule |
|---|---|---|
| S01 `rm -rf tests` | not restored | (b) |
| S02 `sed -i` config | not restored | (b) |
| S03 Write overwrites app.py | restored, to the start of the prompt | (a) |
| S04 new file, then broken by Edit | restored, to the start of the prompt | (a) |
| S05 Bash overwrites logo.png | not restored | (b) |
| S06 Bash `rm .env` | not restored | (b) |
| S07 Bash truncates a 20 MB+ file | not restored | (b) |
| S08 Bash writes outside the project | not restored | (b) |
| S09 bad Edit, then a hand edit to the same file | not documented | (d) says what is captured, not what a restore does to it |
| S10 undo only `rm -rf tests` | not restored | (b) |
| S11 Bash `rm -rf scripts` | not restored | (b) |
| S12 Bash `rm` of a symlink | not restored | (b), (c) |
| S13 no git, Bash `rm -rf tests` | not restored | (b) |
| S14 Write, Edit, `mv`, `sed -i`, Write; back to step 2 | partly: the `sed -i` on app.py (already edited by Claude) and the Writes yes, the `mv` of README.md no | (a), (b) |
| S15 whole session: Edit, then Bash `rm README.md` | partly: the Edit yes, README.md no | (a), (b) |

So by its own documentation, Claude Code's checkpointing would put back the exact state in at most 2 of the
15 (S03, S04, and only when the bad call began its own prompt). This is a reading of documentation, not a
measurement, and must be quoted as such.

## Product gaps the bench exposes, ranked by value in daily work

1. **Git-ignored files (S06): built.** `rm .env`, or a script rewriting `config.local.json`, was a silent
   miss: rewind exited 0 saying it changed nothing. Neither git baseline can do this at all, so it is where
   rewindagents is strictly more useful than git. Done means: S06 exact, and
   `tests/test_bashscan.py::test_a_git_ignored_file_deleted_by_bash_is_put_back` (ignored directories such as
   `build/` still not scanned). Both failed before commit de05532 and pass after.
2. **Executable bit (S11): built.** A deleted script came back with the right bytes, not executable, exit 0.
   Done means: S11 exact, and `test_a_deleted_script_comes_back_executable` (also a `chmod` alone) and
   `test_a_file_the_write_tool_replaced_gets_its_mode_back`. Failed before de05532, pass after.
3. **Undo one step and keep later work, including a hand edit to the same file (S09, S10): next.** Today
   S10 needs `rewind K-1 --only <files>` and S09 is refused (safe, but the user is left to merge by hand).
   A `rewindagents revert K` that three-way merges step K's inverse into the current file (git's
   `merge-file` when available) and refuses on a conflict. Done means: S09 and S10 exact with one command,
   and a conflict test that changes nothing and exits 1.
4. **Symlinks (S12).** A deleted symlink is a silent miss. Done means: S12 exact, plus a test that a rewind
   never writes through a link that points outside the project.
5. **Say so when a command wrote outside the project (S08)** or to a file over the size limit (S07 already
   exits 1). Done means: S08 exits 1 naming the path, even though it is not restored.


## Efficiency pilot (measured, n is small: not a claim)

**Superseded by the pre-registered 190-run study:** `bench/EFFICIENCY_RESULTS.md` (no speed advantage found
for racing three agents; rewind restored the files exactly in 10 of 10 wreck scenarios).

Plan and rules: `bench/EFFICIENCY_PLAN.md`. Nine real Claude Code runs (`claude -p`, Claude Code 2.1.294,
model claude-opus-5-5 as reported, isolated from user hooks and MCP servers) on one task with three seeded
bugs and hidden tests the agent never saw. Raw runs: `bench/efficiency/runs.jsonl`; this table is
`python3 bench/efficiency/pilot.py report`.

Medians over the n runs of each workflow; wall-clock by this script's clock, turns and cost as Claude Code reported them (cost at API list price; the runs used the logged-in account).

| workflow | n | hidden pass | visible pass | median wall s | median turns | median cost USD |
|---|---:|---:|---:|---:|---:|---:|
| solo | 3 | 3/3 | 3/3 | 26.3 | 8 | 0.154 |
| race | 3 | 3/3 | 3/3 | 25.3 | 7 | 0.143 |
| h1-setup-part1 | 1 | 1/1 | 1/1 | 22.7 | 6 | 0.129 |
| h1-resume | 1 | 1/1 | 1/1 | 15.9 | 5 | 0.094 |
| h1-restart | 1 | 1/1 | 1/1 | 26.7 | 7 | 0.149 |
race-015958: K=3, first visible pass after 23.2 s; attempts finished after [23.2, 25.4, 26.6] s

What it shows:

- **H2, parallel attempts:** every single attempt passed the hidden tests (3 of 3 solo, 3 of 3 in the race),
  so there was nothing for a race to save. The first of three concurrent attempts passed after 23.2 s
  against a solo median of 26.3 s (about 1.1 times faster) for the three attempts' combined cost of
  0.43 USD against 0.15 USD (about 2.8 times the cost). On a task an agent already solves every time, racing
  buys little and costs a lot. The case where it could matter, a task one attempt often fails, was not in
  the pilot.
- **H1, resume instead of restart:** after a scripted `rm -rf tests cart.py` wreck, `rewindagents rewind`
  took 0.06 s and the agent then did only the remaining work in 15.9 s (0.094 USD); a restart of the whole
  job took 26.7 s (0.149 USD). Both passed the hidden tests. That is one run each, and the ratio is set by
  how much work lies before the wreck, which the scenario chooses; it is a property of the scenario, not a
  measured speed-up of the tool. What the tool contributes is that the resume is possible at all after a
  shell-command wreck, which Claude Code's documentation says its `/rewind` does not restore (rule (b)
  above).
- **4x:** nothing in the pilot comes near it, and no method was tuned to reach it.

Unmeasured: anything about Cursor or Codex (left out at John's instruction), tasks where one attempt fails
often, H3 (handing the next agent the recorded context), and variance across machines and times of day.

To make a claim solid (needs John's approval: more than the 10-run pilot): 10 tasks of the SWE-bench-Lite
shape picked before any run, calibrated so a share of them have a single-attempt pass rate below 0.8;
per task 5 solo attempts and 5 races of 3; 200 agent runs in all. Publish the per-task and pooled medians of
time to a passing fix, hidden pass rate of the kept attempt, and tokens per passing fix, with the raw log.
