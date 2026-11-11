# rewindagent

Ctrl+Z for AI coding agents: record, replay and rewind. Every tool call your coding agent makes goes into a
tamper-evident, hash-chained log you can verify later.

**Status: v0.0.2, pre-release.** The recorder, its CLI and a Claude Code hook that records every call and
checkpoints files exist today. Replay and rewind are planned; they are listed under Roadmap below and are
not built yet, so a checkpoint can be saved but there is no command to restore it yet.

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

Not checkpointed yet: files changed by `Bash` commands (for example `sed -i` or `rm`). Those calls are
recorded, but the file contents before them are not saved.

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

- Checkpoint files changed by `Bash` commands
- Replay of a recorded session, step by step
- Rewind the working tree to any recorded step, and branch from it

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Licence

Apache-2.0. The hash-chain design is adapted from tinyguard (Apache-2.0).
