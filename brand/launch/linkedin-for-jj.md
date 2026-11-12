# rewindagents: LinkedIn draft for JJ

For JJ only. FIRE never posts to LinkedIn; on launch FIRE emits `fire.launch` on the bus and JJ decides whether,
when and in what words this goes out under John's name. This is raw material: the facts below are the checked
ones, the wording is JJ's to change. Fill the addresses with `python3 brand/launch/fill.py linkedin-for-jj.md`.
Post only after the repository is public (LAUNCH_HOLD is lifted and the launch gate has passed).

## Facts JJ can use

- rewindagents is open source, Apache-2.0, Python standard library only.
- It records every tool call a coding agent makes into a hash-chained log and copies a project file before an edit or a Bash command changes it; the exceptions are git-ignored files, symlinks, files over 20 MB, projects of more than 20,000 files and, outside git, node_modules, .venv, venv and __pycache__.
- Authorship: to confirm with John (state/NEEDS_JOHN.md, 2026-11-12). Hold the post until he gives his own wording; "[authorship line]" in the draft is where it goes.
- `rewindagents replay` lists a session step by step; `rewindagents rewind 12` puts the files back the way they were right after step 12; a rewind can itself be undone.
- It never blocks or changes a call.
- The gap it fills, in the vendor's words: Claude Code's checkpointing docs ({claude_checkpointing_doc}) say "A file that only Bash commands changed isn't tracked and stays as it is." and that subagent edits are usually not in the session's checkpoints. Its rewind does undo Bash changes to a file Claude had already edited. Claude Code runs the same hooks for a subagent's tool calls; rewindagents' subagent path is tested with payloads shaped the way the hooks docs describe, not yet in a live subagent session, so do not claim subagent coverage as proven.
- Claude Code: the hook has run in real sessions. Codex and Cursor: tested with the documented payloads, not yet in a live session.
- Not on PyPI yet. A paid Cloud tier is planned, not built, not priced.

## Draft post

Coding agents are quick with files. Quick enough that the useful question after a bad session is not "what went wrong" but "how do I get step 12 back". The built-in rewind answers that for the agent's own edits. Claude Code's docs say a file only a shell command changed "isn't tracked and stays as it is", and subagent edits are usually missed too.

[authorship line] rewindagents, an open-source undo for coding agents.

A hook records every tool call the agent makes into a hash-chained log, and copies a project file before an edit or a shell command changes it. If the agent runs rm -rf on the wrong folder inside the project, the files it deleted were copied first. The exceptions: git-ignored files, symlinks, files over 20 MB, projects of more than 20,000 files and, outside git, folders like node_modules and .venv.

After a session, one command lists every step. Another puts back the files the later steps changed, the way they were after any step you pick. The rewind is recorded as a step as well, so you can undo the undo.

It never blocks or changes what the agent does. It just keeps the tape.

Works today with Claude Code. Codex and Cursor hooks are tested against their documented payloads, not yet in a live session.

Free and open source: {repo_url}

## Do not

- Do not add numbers (users, stars, downloads, time saved): there are none to quote yet.
- Do not call it a security product, and keep the words in BRAND.md "Words we never use" out.
- Do not tag companies or people who have not used it.
