# rewindagents on Show HN

Draft for launch day; not posted. Fill the addresses with `python3 brand/launch/fill.py show-hn.md`. Post the
title and the URL, then the text as the first comment. Show HN asks for something the poster worked on
personally: how John puts the authorship (built with an AI agent team) is his call before posting. Check the
title fits the submit form on the day.

## Title

Show HN: rewindagents - rewind what your agent's shell commands changed

## URL

{repo_url}

## Text

Claude Code's checkpointing docs ({claude_checkpointing_doc}) are candid about the gap: "A file that only Bash commands changed isn't tracked and stays as it is." And for subagents: "Claude Code usually doesn't capture those edits in your session's checkpoints." (Its rewind does undo Bash changes to a file Claude had already edited.) Claude Code runs the same hooks for a subagent's tool calls as for the main conversation, so a hook can catch both. The subagent path here is tested with payloads shaped the way the hooks docs describe, not yet in a live subagent session.

rewindagents records every tool call a coding agent makes into a hash-chained JSONL log, copies a project file before an edit tool or a Bash command changes it (limits below), and lets you rewind the working tree to any step.

Install and hook it into a project:

```sh
pipx install git+{repo_url}
cd /path/to/your/project
rewindagents install
```

Then, after a session that went wrong:

```sh
rewindagents replay
rewindagents rewind 12 --dry-run
rewindagents rewind 12
```

How it works:

- The Claude Code hook writes a pre record (tool and input) and a post record (tool and response) for every call. Each record holds the SHA-256 of the one before it, so `rewindagents verify` names the first record that was edited, deleted or moved.
- Before Write, Edit, MultiEdit and NotebookEdit it copies the target file into `.rewindagents/objects/`, stored by SHA-256. Around a Bash command it saves a copy of every project file before (each stored once by hash) and scans after, and the post record lists only the files the command changed, created or deleted. A stat cache means unchanged files are not read again.
- A rewind checks the chain and every stored copy it will restore from before it writes anything (a copy that no longer matches is reported and that file left alone), saves the current files first, and records itself as a new step, so it prints the command that undoes it.
- `rewindagents branch 12 --name try2` keeps the current tree on a git branch through a temporary index (your HEAD and index stay as they were), then rewinds.
- The hook never blocks or changes a call and always exits 0; it prints nothing, except the replies Cursor's hook protocol requires: {"permission": "allow"} before a call and {} after one. The CLI makes no network connections. Standard library only, Python 3.10 or newer, on a Unix (it uses a file lock).

Limits, since you will ask: files over 20 MB are noted, not copied. Symlinks are not saved. A project of more than 20,000 files is not scanned around a Bash call; the call is still recorded and rewind reports it. Only the project directory is scanned, and git-ignored files are left out. A hash chain alone cannot tell that records were cut off the end or that the whole file was rewritten and re-hashed, so `rewindagents verify --head <pinned-hash>` checks against a head hash you keep somewhere the agent cannot write.

Status: the Claude Code hook has run in real sessions. The Codex and Cursor hooks are built from the vendors' hook documentation and tested with the documented payloads, not yet in a live session. If you run either and the payload differs, an issue with the payload would help a lot. Not on PyPI yet. A hosted tier is planned, not built, not priced.

Apache-2.0. Feedback welcome on files outside the project: right now a file outside it that an edit tool changed is reported and left alone, and a shell command's changes outside the project are not seen at all.

made by John B Joseph
