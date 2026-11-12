# rewindagents on Product Hunt

Draft for launch day; not posted. Fill the addresses with `python3 brand/launch/fill.py producthunt.md`.
Every command below is one of the README's; tests/test_launch.py checks each one. The maker comment is written
without "I built": how the authorship is put (John, with an AI agent team) is John's call before posting.

## Name

rewindagents

## Tagline

Ctrl+Z for AI coding agents: record, replay, rewind

## Description

An open-source recorder for coding agents. Every tool call goes into a hash-chained log, and a project file is copied before an edit or a Bash command changes it. Replay a session, rewind the files to any step, undo the rewind. Apache-2.0.

## Topics

Developer Tools, Open Source, Artificial Intelligence, GitHub

## Links

- Website: {site_url}
- Repository: {repo_url}

## Maker comment

Hi Product Hunt. rewindagents exists because coding agents change files fast, often through shell commands, and every one of those steps should be undoable.

What it does today:

- A hook for Claude Code records every tool call into `.rewindagents/log.jsonl`, one hash chain, and copies a project file before Write, Edit, MultiEdit, NotebookEdit or a Bash command changes it. The exceptions: git-ignored files, symlinks, files over 20 MB, projects of more than 20,000 files, and, outside a git repository, node_modules, .venv, venv and __pycache__.
- `rewindagents replay` lists the session one line per step. `rewindagents rewind 12` puts back the files the later steps changed, the way they were right after step 12. The rewind is itself a step, so it can be undone.
- `rewindagents export` writes a session as one HTML page, `rewindagents sessions --grep config.py` finds sessions, and `rewindagents bundle --out s1.bundle` carries one to another machine.
- It never blocks or changes a call, and the hook always exits 0.

What it does not do yet, said plainly: it is not on PyPI yet (install it from the repository with pipx). The Codex and Cursor hooks are built from the vendors' hook documentation and tested with the documented payloads, not yet in a live session. A paid Cloud tier (cloud sync, shareable replay links, long retention, session search) is planned, not built and not priced.

The clip in the gallery is a real session: fourteen agent steps through the hook, the last two delete the tests and overwrite the config, and one rewind puts the four files back. The repository has the script that recorded it.

If a real Codex or Cursor session sends a payload the hook does not expect, please open an issue with it. That is the most useful thing anyone could send.

## Gallery

Five images, 1270 x 760 (Product Hunt's recommended size), in brand/launch/ph-1.png to ph-5.png, built by
brand/launch/gallery.py from the recorded session, the README, the one-line promise in BRAND.md, this list and
the logo set. An independent critic scores them in brand/launch/review.json; read the verdict there before
uploading.

1. The name, the tagline and the mark.
2. `rewindagents replay`: the end of the fourteen steps, the last two marked; the first nine are folded into one tick each.
3. `git status --short` after the wreck: the deleted tests.
4. `rewindagents rewind 12`: four files restored, and the undo line.
5. Install in two commands: pipx from the repository, then `rewindagents install` in the project.

made by John B Joseph
