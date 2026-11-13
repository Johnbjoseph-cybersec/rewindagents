# takeback-bench results

## Measured: current code

<!-- takeback:current:start -->
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
