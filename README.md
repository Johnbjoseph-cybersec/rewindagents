# rewindagent

Ctrl+Z for AI coding agents: record, replay and rewind. Every tool call your coding agent makes goes into a
tamper-evident, hash-chained log you can verify later.

**Status: v0.0.7, pre-release.** Built and tested today: the recorder and its CLI, hooks for Claude Code,
Codex and Cursor that record every call and checkpoint the files a step changes, `replay`, `rewind` and
`branch`, `export` (a session as one HTML page), `sessions` (list and search the sessions in a log),
`bundle` and `import` (carry a session to another machine or clone as one file), `gc` (delete stored file
copies nothing names any more), and a pip-installable package with a `rewindagent` command. Not on PyPI yet. The Claude Code hook has run in real
sessions; the Codex and Cursor hooks are built from the vendors' hook documentation and tested with the
documented payloads, not yet in a live session.

![rewindagent demo: an agent's last two steps delete the tests and overwrite the config; rewindagent replay lists the fourteen steps, rewindagent rewind 12 puts the files back](brand/demo.gif)

The clip is a real session, not a mock-up: `brand/demo/build.py` runs fourteen agent steps through the
hook in a temporary project, then the four commands shown, and draws the frames from what they printed.
`tests/test_demo.py` plays the same session again and fails if any line differs.

## Install

Python 3.10 or newer (declared in `pyproject.toml`; tested on 3.15, macOS). No dependencies beyond the
standard library. From the repository:

```sh
pipx install git+https://github.com/Johnbjoseph-cybersec/rewindagent     # or: pip install git+https://...
rewindagent --version
```

Or from a clone, `pip install .`. Without installing, `PYTHONPATH=src python3 -m rewindagent` runs the same
CLI from a clone.

## Claude Code hook

```sh
cd /path/to/your/project
rewindagent install            # adds the hook to .claude/settings.json in this project
rewindagent install --settings ~/.claude/settings.json   # or for every project
```

`install` keeps everything already in the settings file and does nothing if the hook is already there. The
hook command it writes names the Python that rewindagent was installed into by absolute path, so it runs
whether or not a virtualenv is active; from an uninstalled clone it carries the `PYTHONPATH` instead.
After that, in each project Claude Code works in:

- every tool call gets a `pre` record (tool and input) and a `post` record (tool and response) in
  `.rewindagent/log.jsonl`, in one hash chain. Responses longer than 4,000 characters are cut, with the
  full length noted.
- before `Write`, `Edit`, `MultiEdit` and `NotebookEdit`, the current bytes of the target file are copied
  to `.rewindagent/objects/<sha256>` and the hash goes into the `pre` record. A file that does not exist
  yet is recorded as absent. Files over 20 MB are noted and not copied.
- `.rewindagent/` gets its own `.gitignore`, so the log and the copies stay out of your commits.

The hook never blocks or changes a call. It prints nothing and always exits 0, even if its input is
broken or it cannot write; any problem goes to stderr only.

Around every `Bash` call (for example `sed -i`, `rm`, `mv`, a code generator), the hook saves the
project's files before the command, scans again after it, and checkpoints, in the `post` record, only the
files that were changed, deleted or created. Details and limits:

- "The project's files" means, in a git repo, what `git ls-files --cached --others --exclude-standard`
  lists: tracked and untracked files, but not git-ignored ones. Outside git, every file under the project
  directory except `.git`, `.rewindagent`, `node_modules`, `.venv`, `venv` and `__pycache__`.
- Only the project directory is scanned. A command that changes files elsewhere is recorded, not saved.
- Symlinks are not saved. Files over 20 MB are noted and not copied.
- Copies are stored by SHA-256, so an unchanged file is stored once. A stat cache
  (`.rewindagent/index.json`) means only files whose size or modification time changed are read again.
- A project with more than 20,000 files is not scanned; the call is still recorded and `rewind` reports it.

## Codex and Cursor hooks

```sh
rewindagent install --agent codex      # adds the hook to .codex/hooks.json in this project
rewindagent install --agent cursor     # adds the hook to .cursor/hooks.json in this project
rewindagent install --agent cursor --settings ~/.cursor/hooks.json   # or for every project
```

Same recorder, same log, same `replay`, `rewind`, `branch`, `export` and `sessions`. What differs is how each
agent calls the hook, and `src/rewindagent/agents.py` quotes the vendor documentation (read 2026-11-11) it was
built from:

- Codex (`.codex/hooks.json`, the same file shape as Claude Code's settings) sends `PreToolUse` and
  `PostToolUse` with `session_id`, `cwd`, `tool_name`, `tool_use_id`, `tool_input` and `tool_response`; shell
  commands arrive as `Bash` and file edits as `apply_patch`. Codex asks you to trust a new hook before it runs
  (`/hooks` inside Codex) and remembers the trust by the hook's hash, so a hook command that changes needs
  trusting again. Project hooks load only when the project's `.codex/` folder is trusted.
- Cursor (`.cursor/hooks.json`) sends `preToolUse` and `postToolUse` with `conversation_id` (used as the
  session), `cwd`, `tool_name`, `tool_input`, `tool_use_id` and, after the call, `tool_output`; its tools are
  `Shell`, `Read`, `Write`, `Grep`, `Delete`, `Task` and `MCP:<name>`. Cursor's `preToolUse` is a permission
  hook that treats an empty or invalid answer as a failure, so for Cursor the hook prints
  `{"permission": "allow"}` before a call and `{}` after one. "allow" is the one answer that changes nothing;
  a deny from any other hook still wins.
- The input of Codex's `apply_patch` and Cursor's `Write` is not documented, so the hook never reads a file
  path out of a Codex or Cursor payload. Instead, around every Codex or Cursor call except the tools the docs
  name that cannot change files (Cursor's `Read` and `Grep`, Codex's `update_plan`), the project is saved
  before the call and scanned after it, exactly as around a `Bash` command, and only the files the call
  changed, created or deleted are checkpointed. The cost is a stat of every project file per call; unchanged
  files are not read again. The same 20 MB and 20,000-file limits apply.
- Verified so far: the hook driven by the payloads in the vendors' documentation, in `tests/test_agents.py`
  and through the installed binary in `tests/test_installed.py`. Not yet in a live Codex or Cursor session.
  If a real session sends something else, open an issue with the payload (`replay --step N` prints what
  was recorded).

## Replay, rewind, branch

Run these from the project directory (the one holding `.rewindagent/`). They work on the latest session
unless you pass `--session ID`.

```sh
rewindagent replay              # one line per step: number, tool, file or command
rewindagent replay --step 12    # step 12 in full: input, checkpoints, result
rewindagent rewind 12 --dry-run # what would change
rewindagent rewind 12           # files back to how they were right after step 12
rewindagent branch 12 --name try2   # keep the current files, then rewind to step 12
```

- `rewind N` puts back every file that a step after N changed with `Write`, `Edit`, `MultiEdit`,
  `NotebookEdit` or a `Bash` command, and deletes the files those steps created. `rewind 0` undoes the
  whole session.
- A rewind is undoable. It first saves the current bytes of every file it will change and records itself
  as a new step; the command prints `undo it with: rewindagent rewind <step> --session <id>` (from an
  uninstalled clone it says `python3 -m rewindagent` instead).
- `branch N --name X` does the same and, in a git repo, also commits the whole current working tree to the
  branch `rewindagent/X`. It does this through a temporary index, so your `HEAD`, index and current
  branch stay as they were. Outside git, the current files are kept in the log only.
- Before writing anything, rewind checks the log's hash chain and the SHA-256 of every stored copy. If the
  chain is broken it changes nothing. If a stored copy no longer matches, that file is reported and left
  as it is.
- It only touches files inside the project directory. Files outside it are reported and left alone.
- Limits: a step whose before/after scan did not finish (a `Bash`, `Shell` or `apply_patch` call in a project
  of more than 20,000 files, or one whose post event never arrived) is counted and reported, and its changes
  are not put back. Directories created by
  later steps stay (empty). Files over 20 MB were never copied, so they are reported and not restored. If
  anything could not be restored, the exit code is 1.

## Export a replay

```sh
rewindagent export                                  # writes .rewindagent/replay-<session>.html
rewindagent export --session abc --out replay.html  # a given session, to a given file
rewindagent export --no-contents                    # steps, tools and paths only: no inputs, results or diffs
```

One HTML file with the whole session: every step with its tool, input and result, and for every file a
step checkpointed, the change that step made as a unified diff (the file before the step against the file
after it: its next checkpoint in the session, or the file as it is now). Open it in a browser, attach it to a
bug report or a code review, or keep it with the session.

- Inline CSS only. No scripts, and nothing is fetched from anywhere, so the page is safe to pass on.
- Paths inside the project are shown relative to it; where the project lives on disk is not in the page.
- A file over 256 KB on either side is described, not diffed. A diff longer than 400 lines is cut, with
  the count of the lines left out. Binary files show their size before and after.
- Inputs and results are the recorded ones, so a result that was cut at 4,000 characters stays cut.
- `--no-contents` drops inputs, results and diffs (a `Write` input is the file's content). Each step keeps
  the one-line summary `replay` prints, so a `Bash` command line is still on the page.
- If the log's hash chain does not verify, the page is still written, with a notice naming the first bad
  record, and the command exits 1.

## Find a session

```sh
rewindagent sessions                     # every session in the log: id, first and last time, steps, files touched
rewindagent sessions --grep config.py    # only sessions with a step that mentions it, and those steps
```

One line per session, in the order the sessions first wrote to the log, with the session id, the local
time of its first and last record, the number of steps (the numbers `replay` and `rewind` use, with how
many of them are rewinds or branches) and the files it touched; a second line names the first 5 files and
counts the rest. The session that wrote the
last record, the one `replay` and `rewind` use by default, is marked `(latest)`.

- A file is touched when a step checkpointed it: changed, created or deleted by `Write`, `Edit`,
  `MultiEdit`, `NotebookEdit`, a `Bash` command or a rewind. A file that was only read is not touched.
- `--grep TEXT` keeps the sessions with a step whose `replay` line (the command, the file, or the
  input) or checkpointed path contains TEXT, in any case, and lists those steps under the session with
  their step numbers, so `rewindagent rewind <step> --session <id>` can follow. Exit code 1 if no session
  matches.
- Paths are shown relative to the project.

## Move a session to another machine

```sh
rewindagent bundle --out s1.bundle                 # the latest session, and the file copies it names, in one file
rewindagent bundle --session abc --out abc.bundle  # a given session
rewindagent import s1.bundle                       # in another clone: check the file, then add the session to its log
```

Then `replay`, `rewind` and `branch` work on that session in the other clone, with `--session <id>`.

- One JSON file: the session's log records exactly as the log holds them, each with its hash, and every
  stored file copy they name. Nothing goes over a network; carry the file however you like.
- `bundle` refuses a log whose chain does not verify, and a session whose stored copies are missing or altered.
- `import` writes nothing until everything checks out: the file's own SHA-256, every record's hash, that every
  record belongs to the session and is in log order, every stored copy against its SHA-256, that no copy a
  record names is missing, that this project's log verifies, and that it does not already hold the session.
- The records join this project's chain in order, with their original times; they get new sequence
  numbers and hashes here.
- File paths under the old project move under this one, so a rewind puts the files back in this clone.
  Commands and results keep their text as recorded.

## Clean up stored copies

```sh
rewindagent gc --dry-run   # what would be deleted, and how many bytes
rewindagent gc             # delete it
```

Before every Bash call the hook saves a copy of every project file, and afterwards the log names only the
copies of files the command changed, so `.rewindagent/objects/` grows. `gc` deletes every stored copy that no
log record (in any session) and no pending scan (a command whose after-scan has not run) names, and prints how
many it deleted and the bytes those files took on disk.

- Every step of every session in the log can still be rewound afterwards; the copies a rewind needs are the
  ones the log names.
- It refuses to run when the log does not verify, and it never writes to the log.
- While it runs it holds the store lock, so a hook call waits for it to finish, and it waits (up to 30 s) for
  a hook, rewind or import that has saved a copy but not yet written the record naming it.

## Recorder

- `Recorder.record(session, tool, args, result)` appends one JSON line per tool call.
- Each record holds the SHA-256 of the record before it, so editing, deleting or reordering any
  record makes `verify` fail and name the first bad record.
- Several processes can write to the same log at once; appends are locked, so the chain stays single.
- Plain JSONL. No server, no database, no dependencies beyond the Python standard library.
  Needs a Unix (`fcntl`) for the write lock.

## Use it

```sh
echo '{"tool": "Bash", "args": {"command": "ls"}}' | rewindagent record --session s1
rewindagent verify     # OK: 1 records, chain intact
rewindagent show       # list recorded calls
rewindagent head       # current head hash
```

The log defaults to `.rewindagent/log.jsonl`; change it with `--log PATH`.

From Python:

```python
from rewindagent import Recorder, verify
Recorder("log.jsonl").record("s1", "Bash", {"command": "ls"}, {"exit": 0})
print(verify("log.jsonl"))   # (True, 1, 'chain intact')
```

## What the chain does not catch

A hash chain proves the records are unchanged *relative to each other*. It cannot, on its own, tell
that records were cut off the end, or that someone rewrote the whole file and re-hashed every line.
To catch both, copy the head hash somewhere the agent cannot write (`rewindagent head`) and check
against it:

```sh
rewindagent verify --head <pinned-hash>
```

## Roadmap

- Publish on PyPI
- Run the Codex and Cursor hooks in live sessions and keep the real payloads as test fixtures
- A paid Cloud tier (cloud sync, shareable replay links, long retention, session search): planned, not built,
  not priced. The waitlist is a GitHub issue on this repository with the label `waitlist`; say what you would pay for.

## Payments code (not live)

`billing/polar.py` is the checkout and webhook code for that Cloud tier, written against Polar's API documentation
(the pages and the date are cited at the top of the file). It is not part of the `rewindagent` package and is never
installed with it; the CLI itself makes no network connections. No product exists yet, so nothing can be bought.

```sh
python3 billing/polar.py link --product <id>              # a reusable checkout link, printed
python3 billing/polar.py checkout --product <id>          # a single-use checkout session, printed
python3 billing/polar.py verify --headers h.json --body b.json   # check a saved webhook delivery
```

- The sandbox (`sandbox-api.polar.sh`) unless `--production` is given. The token is read from
  `POLAR_ACCESS_TOKEN` and the webhook secret from `POLAR_WEBHOOK_SECRET`; neither is ever an argument, and
  error messages replace the token with `[token]`.
- `link --write-config` also sets `checkout_url` in `brand/site/config.json`, which turns the pricing page's
  waitlist button into a buy button. The return address after paying comes from `site_url` in the same file.
- `verify` checks the Standard Webhooks signature (HMAC-SHA256 over `id.timestamp.body`) with both keys Polar
  documents (secrets made before 8 September 2026 use the whole secret string as the key), and refuses a
  timestamp more than 5 minutes from now. The 5 minutes is our choice; Polar does not give a number.
- Tested in `tests/test_polar.py` with a fake network; it has not yet talked to Polar's sandbox.

## Site

`brand/site/` holds the landing page, the pricing page and the getting-started docs, published with GitHub Pages
by `.github/workflows/pages.yml`. The pages are built by `brand/site/build.py` from this README, the package and
the clip's session, and `tests/test_site.py` fails if a committed page differs from a fresh build. The site's
address lives in one place, `brand/site/config.json`.

`brand/vsl/` holds the scripts and captions of the launch videos, rendered by `brand/vsl/build.py` from
`brand/vsl/beats.json`; every command and terminal line in them is one of this README's or one the clip's session
printed, and `tests/test_vsl.py` checks that. The videos themselves are not made yet.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

That runs against the source tree and skips the tests of the installed command. `.fire-test-cmd` holds the
full command: it builds `.venv`, installs the package into it and runs every test, including the ones that
drive the installed `rewindagent` binary and the hook command it writes into a settings file.

## Licence

Apache-2.0. The hash-chain design is adapted from tinyguard (Apache-2.0).
