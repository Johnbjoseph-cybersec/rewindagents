# Hook speed, branch perf/10x (stdlib only, behaviour unchanged)

Same sitting, same machine (Apple M6, Python 3.15.2), `python3 bench/hook_overhead.py --files 100 1000 10000 --runs 7`.
Before = release 1ac5f23 in a separate worktree; after = this branch. Load average 3.6 at the start of both runs
(1-min 3.56 / 3.57 at the start of before / after; files `load_before.txt`, `load_after.txt`). Median per tool call
(Pre + Post processes), 90th-percentile-ish max in brackets. Raw: `before.json/.txt`, `after.json/.txt`.

| Files | Read before -> after | Edit before -> after | Bash before -> after | First Bash before -> after |
|---:|---:|---:|---:|---:|
| 100 | 65 -> 39 ms | 68 -> 38 ms | 116 -> 67 ms | 134 -> 84 ms |
| 1,000 | 77 -> 36 ms | 76 -> 36 ms | 158 -> 69 ms | 276 -> 188 ms |
| 10,000 | 76 -> 41 ms | 74 -> 40 ms | 368 -> 151 ms | 2,692 -> 1,834 ms |

One hook process (Read, Pre), 60 runs, quiet machine: 33 ms -> 18 ms. `python -c pass` is about 10 ms, so the
floor for a call is two Python starts, about 20 ms.

## What changed
1. `__main__.py`: `hook` and `hook --agent X` / `--agent=X` go straight to `hook.run`; the CLI (argparse, bundle,
   export, rewind, runs, ui...) is not imported. Any other argv, and an unknown agent name, still goes through
   cli/argparse, so every message is unchanged. The `python <clone>/src/rewindagents/__main__.py hook` file form
   reaches the same code (it re-runs the module as a package). The installed command
   `<venv python> -m rewindagents hook` is unchanged and gets the speedup; no re-init needed.
2. `__init__.py` is lazy (PEP 562 `__getattr__`): `from rewindagents import Recorder, read, verify, head, GENESIS`
   still works; `__version__` is eager. This removes log -> rewind -> tempfile/subprocess/shutil from every start.
3. Hook-start imports trimmed: `typing` (annotations only), `re`/`shlex` compiled/imported on first use in
   hook.py, `subprocess` only when a Bash scan runs, SHA-256 from CPython's built-in `_sha2` (3.12+; falls back
   to `hashlib`) instead of `hashlib`, which loads OpenSSL (about 1.6 ms). Digests are identical.
4. Bash scan (bashscan.py), the dominant cost at 10k files: per file the old code did `is_symlink`, `is_file`,
   `stat` (pathlib objects, 4+ syscalls) and, in the pre scan, a stat to see if the object exists. Now: one
   `os.lstat` per file (also tells symlink/regular), its result reused for the index check; object existence
   from one `listdir` of the store; the three `git ls-files` calls run concurrently (threads); SKIP_DIRS test on
   the string; `index.json` is not rewritten when unchanged. In-process pre scan at 10k files: 320 -> 67 ms,
   post scan: 244 -> 72 ms (cProfile run). What is checkpointed is unchanged: same file list, same limits
   (20,000 files, 20 MB), changed/created/deleted/chmod detection, symlinks skipped.

## Proof
- Tests: `python3 -m unittest discover -s tests` (the CI command). Baseline 1ac5f23: 851 tests OK (24 skipped).
  Branch: 856 tests, OK (24 skipped), twice from cleared __pycache__ (`tests_final_1.txt`, `tests_final_2.txt`; the two earlier runs failed only on the site counter before the rebuild).
  New: `tests/test_hook_fastpath.py` (5 tests: no cli/rewind/argparse/subprocess imported by the hook; four
  invocation forms record and exit 0; Gemini answer `{}`; bad agent still argparse exit 2; package attributes).
  Adding tests moves the site's test counter; `brand/site/index.html` was rebuilt with `brand/site/build.py`
  (one number, 833 -> 838) because `test_site` checks it byte for byte.
- `compare_old_new.py` (output `compare_old_new.out`): the same scripted session (Read, Edit, Write, Bash with rm
  of a tracked file and a gitignored `.env`, sed -i, chmod -x, new file; Cursor and Gemini events; a bad payload;
  a missing cwd) run through the old and new hook in fresh git repos. Exit codes, stdout, stderr, and all 12
  records are identical once ts/hash/prev are removed; `rewindagents verify` passes on both ("chain intact");
  `rewind 3` restores identical trees (deleted file and `.env` back, mode 755 back, new file removed).
  Existing tests that cover the same ground: test_hook, test_hook_hardening, test_bashscan, test_background,
  test_rewind, test_log, test_recording_gaps.

## What remains
The floor is two Python starts (about 10 ms each) plus json/re/pathlib/threading imports (about 6 ms in all).
First Bash on 10k files is still 1.8 s: it hashes and copies every file once, which is the checkpoint itself.

## Not done
- Console script `rewindagents hook` (entry point `cli:main`) still imports the CLI; it is not the installed
  command. Making cli lazy is a larger refactor.
- No `python -S`/`-I` or flag changes to the written command (breaks venv/site layouts); init still writes the
  same command, so old and new installs behave alike.
- Replacing `dataclasses` in agents.py (about 0.3 ms net) and avoiding json's `re` import (would mean a custom
  JSON path; byte-for-byte risk) were skipped as not worth the risk.
- bench/results.json and README numbers are untouched (owner republishes).
