# Shell-step capture up to 2,000,000 files (branch perf/2m, from perf/10x de0b037)

Stdlib only; git (the user's own binary) is the only helper, as bashscan already used it. No daemon of ours.

## Result (Apple M6, load average 8 to 18 from other sessions: absolute numbers are noisy, medians of 7)

Per Bash call = Pre + Post hook process together, with one `sed`-style edit between. Raw: `scale_*.json`.

| Project | Old scan | Git path, first call | Git path, warm median | Read / Edit |
|---|---|---|---|---|
| 10,000 files (git) | 131 ms (first 435) | 167 ms | 133 ms | 39 / 38 ms, unchanged |
| 645,712 tracked files (clone of the real tree, 125k dirs) | cap 20,000: not checkpointed | 11.3 s (cold) | 5.9 s | 42 / 61 ms |
| 2,000,000 files (2,000 dirs of 1,000) | cap 20,000: not checkpointed (13 s if it scanned) | 14.0 s (cold: no fsmonitor daemon) | 2.0 s | 41 / 43 ms |
| same, `REWINDAGENTS_IGNORED=skip` | | 6.6 s (2M), 1.9 s (646k) | 1.1 s (2M), 1.2 s (646k) | 40 / 40 ms |

Up to 20,000 tracked files the old scan is kept: it is as fast (131 vs 133 ms at 10k, measured both ways) and exact.
At 10k the git path is not faster on the warm call, but its first call is (167 vs 435 ms: it reads no clean file).

Where the time goes at scale: `git status` twice per call. Without the ignored-file listing it is 0.14 s at 2M; the
listing of files git ignores one by one (`.env`, `*.log`: today's rule, kept) makes git walk every directory, which
no cache helps (0.8 s at 2M, 3 s over the 125k directories of the real tree, about the cost of `find`). That is the
dominant cost; `REWINDAGENTS_IGNORED=skip` drops it and, with it, the checkpoint of ignored single files.

The 646k tree: `~/standards-contributions` is not itself a git repository, and today has 651k files, not 356k.
The test repo is an APFS clone (`cp -c -R`, never written in the original) with the nested `.git` dirs and files
over 256 KB removed, indexed with `update-index --info-only` (no blobs written, to save disk), 645,712 tracked.
Only the four files the script touches had blobs written (`git hash-object -w`).

## Proof
- Suite: `python3 -m unittest discover -s tests`, 891 tests OK (24 skipped), run twice from cleared `__pycache__`
  (`tests_run1.txt`, `tests_run2.txt`). Baseline perf/10x: 856. 35 new tests in `tests/test_gitscan.py`.
  The site's test counter changed again (838 to 873), `brand/site/index.html` rebuilt with `brand/site/build.py`.
- Same session, both paths (`compare_scan_paths.py`, 10,000-file repo, output `compare_scan_paths.out`): rm of a
  tracked file, `sed -i`, create, `git mv`, a tracked file dirty before and edited again, an untracked file edited,
  a file staged then changed again, an ignored `.env` removed, an ignored log appended, `chmod -x`, a file made in an
  ignored directory. Checkpoints: 12 and 12, byte-identical; "after" entries identical; rewind text identical; both
  restore the tree exactly (the file made in the ignored `build/` stays, by rule, on both).
- Rewind at scale (`proof` in each JSON): `rm` one tracked file and `sed -i` another (dirty before), then
  `rewind 0`: both restored byte for byte and mode, at 2M files and on the 646k tree (`restored_equal: true`).

## How it works (gitscan.py)
Before: `git status --porcelain=v2 -z` (untracked files individually, ignored files one by one, no renames, submodules
ignored) lists what is already dirty (D0); those files go into the store as today; HEAD is recorded. Clean files are
not read: their bytes are HEAD's. After: status again (D1), plus `git diff-tree` between the two HEADs if HEAD moved.
Only D0, D1 and that difference can have changed; each is compared with its state before (the pending hash for D0,
else its blob in the old HEAD, put in the store only if the command changed it). Checkpoint and "after" entries,
pending-scan layout (gc reads it unchanged: the git metadata sits under a key no path can have), and the rewind
side are the same. The pre record gains `"git": true`.
Speed-ups per command with `-c`, never written to the repository's config: `core.untrackedCache=true` from 50,000
tracked files, git's built-in `core.fsmonitor=true` from 200,000 (tried, dropped on failure). They need `-unormal`
to help the untracked part; the ignored listing needs `-uall`, so by default the untracked cache gives nothing and
fsmonitor does the work (8 s plain status at 2M, 0.9 s with fsmonitor).

## Edge cases (each has a test in test_gitscan.py)
| Case | Behaviour |
|---|---|
| HEAD moves (checkout, reset --hard, stash, commit, first commit) | handled, not a fallback: files that differ between the two HEADs join the candidates; pre-state is the old HEAD's blob |
| staged then changed again; tracked dirty; untracked before | pre-state is the working file copied before the command |
| renames (git mv, mv), tracked deletes, creates | same checkpoints as the old scan |
| ignored directories | not scanned (rule kept); ignored single files are (`.env`) |
| untracked files under SKIP_DIRS | not scanned, as before; tracked ones are |
| submodules | a directory: contents not scanned, as before |
| `git add`, `git commit` run by the command | no worktree change = no checkpoint; commit handled via HEAD diff |
| repository without commits | staged and untracked files are all "dirty"; first commit handled |
| CRLF/eol/ident/`filter` | **fallback to the exact old scan** when a conversion is configured (autocrlf true/input, or text/eol/ident/filter in the root .gitattributes, .git/info/attributes, core.attributesFile) and the project has at most 20,000 files. Above that, a clean file's pre-state is `git cat-file --filters` (what checkout writes; exact except a clean file with mixed endings); a nested .gitattributes is checked per changed file the same way; an external `filter=` file is recorded as skipped, not guessed |
| file over 20 MB | recorded as skipped, as before (also when only the old HEAD blob is that large) |
| executable bit | restored from the tree mode (permission bits other than x come from the umask for a deleted clean file; the old scan knew the real ones) |
| project below the top of a repo, not a repo, git missing/failing | old scan and its 20,000 limit |
| more than 2,000,000 tracked files | `skipped: more than 2,000,000 files`; `status` warns (reads the index header, no scan) |
| more than 200,000 dirty/untracked/ignored files, or differing between two HEADs | skipped with the reason |

## Limits and things worth knowing
- Files marked `skip-worktree` / `assume-unchanged` are invisible to git status and so to this path.
- A clean file deleted by the command gets its mode from the umask and the git exec bit, not its real mode.
- git's fsmonitor token is dropped by any git command that rewrites the index without `core.fsmonitor` set (the
  user's own `git add`, `git commit`, `git checkout`): the next hook call then pays a full status (8 to 14 s at 2M;
  seen in the cold rows). For projects this size run `git config core.fsmonitor true` once; this tool does not
  change the user's config. The fsmonitor daemon git starts stays running until `git fsmonitor--daemon stop`.
- `core.untrackedCache` trusts directory mtimes: fine on APFS/ext4/NTFS, not on network file systems.
- Not done: parallel ignored-file listing (measured: no gain, one directory dominates and every process reloads
  the index), caching the ignored list between calls (a file made between two calls would be missed).
- README says 20,000; not edited (owner republishes). `bench/results.json` untouched.
