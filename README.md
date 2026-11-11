# rewindagent

Ctrl+Z for AI coding agents: record, replay and rewind. Every tool call your coding agent makes goes into a
tamper-evident, hash-chained log you can verify later.

**Status: v0.0.4, pre-release.** Built and tested today: the recorder and its CLI, a Claude Code hook
that records every call and checkpoints the files that `Write`/`Edit` and `Bash` commands change, and
`replay`, `rewind` and `branch`. Not built yet: a pip package (see Roadmap).

## Claude Code hook

There is no pip package yet. From a clone:

```sh
git clone https://github.com/Johnbjoseph-cybersec/rewindagent
export PYTHONPATH="$PWD/rewindagent/src"
cd /path/to/your/project
python3 -m rewindagent install            # adds the hook to .claude/settings.json in this project
python3 -m rewindagent install --settings ~/.claude/settings.json   # or for every project
```

`install` keeps everything already in the settings file and does nothing if the hook is already there.
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

## Replay, rewind, branch

Run these from the project directory (the one holding `.rewindagent/`). They work on the latest session
unless you pass `--session ID`.

```sh
python3 -m rewindagent replay              # one line per step: number, tool, file or command
python3 -m rewindagent replay --step 12    # step 12 in full: input, checkpoints, result
python3 -m rewindagent rewind 12 --dry-run # what would change
python3 -m rewindagent rewind 12           # files back to how they were right after step 12
python3 -m rewindagent branch 12 --name try2   # keep the current files, then rewind to step 12
```

- `rewind N` puts back every file that a step after N changed with `Write`, `Edit`, `MultiEdit`,
  `NotebookEdit` or a `Bash` command, and deletes the files those steps created. `rewind 0` undoes the
  whole session.
- A rewind is undoable. It first saves the current bytes of every file it will change and records itself
  as a new step; the command prints `undo it with: python3 -m rewindagent rewind <step> --session <id>`.
- `branch N --name X` does the same and, in a git repo, also commits the whole current working tree to the
  branch `rewindagent/X`. It does this through a temporary index, so your `HEAD`, index and current
  branch stay as they were. Outside git, the current files are kept in the log only.
- Before writing anything, rewind checks the log's hash chain and the SHA-256 of every stored copy. If the
  chain is broken it changes nothing. If a stored copy no longer matches, that file is reported and left
  as it is.
- It only touches files inside the project directory. Files outside it are reported and left alone.
- Limits: a `Bash` step whose scan did not run (more than 20,000 files, or Claude Code sent no
  `PostToolUse` for it) is counted and reported, and its changes are not put back. Directories created by
  later steps stay (empty). Files over 20 MB were never copied, so they are reported and not restored. If
  anything could not be restored, the exit code is 1.

## Recorder

- `Recorder.record(session, tool, args, result)` appends one JSON line per tool call.
- Each record holds the SHA-256 of the record before it, so editing, deleting or reordering any
  record makes `verify` fail and name the first bad record.
- Several processes can write to the same log at once; appends are locked, so the chain stays single.
- Plain JSONL. No server, no database, no dependencies beyond the Python standard library.
  Tested on Python 3.15 on macOS; needs a Unix (`fcntl`) for the write lock.

## Use it

```sh
git clone https://github.com/Johnbjoseph-cybersec/rewindagent && cd rewindagent
export PYTHONPATH=src

echo '{"tool": "Bash", "args": {"command": "ls"}}' | python3 -m rewindagent record --session s1
python3 -m rewindagent verify     # OK: 1 records, chain intact
python3 -m rewindagent show       # list recorded calls
python3 -m rewindagent head       # current head hash
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
python3 -m rewindagent verify --head <pinned-hash>
```

## Roadmap

- A pip package with a `rewindagent` console command

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Licence

Apache-2.0. The hash-chain design is adapted from tinyguard (Apache-2.0).
