# rewindagent

A flight recorder for AI agents. Every tool call your coding agent makes goes into a
tamper-evident, hash-chained log you can verify later.

**Status: v0.0.1, pre-release.** Only the recorder and its CLI exist today. The Claude Code hook,
policy blocking and session replay are planned; they are listed under Roadmap below and are not built yet.

## What works now

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

- Claude Code `PreToolUse` / `PostToolUse` hook that records every call
- Policy rules that block a call before it runs (for example `rm -rf /`, force-push, production DB writes)
- Replay of a recorded session

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Licence

Apache-2.0. The hash-chain design is adapted from tinyguard (Apache-2.0).
