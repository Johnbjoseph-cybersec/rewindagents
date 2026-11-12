# rewindagents on Reddit

Draft for launch day; not posted. Fill the addresses with `python3 brand/launch/fill.py reddit.md`.
Before posting in a subreddit, open it on Reddit itself and read its rules in the sidebar: some allow a project post
only on a set day or only from accounts that take part there. One post per subreddit, never cross-posted the same
hour, and stay in the thread to answer. How the authorship is put (John, with an AI agent team) is John's call
before posting.

## Subreddits

- r/ClaudeAI: lead with the Claude Code hook, the one that has run in real sessions.
- r/ChatGPTCoding: lead with the Codex hook, and say it is tested with the documented payloads, not yet in a live session.
- r/cursor: lead with the Cursor hook, and say the same.

## Title

An undo for coding agents that also rewinds the files only a shell command changed

## Body

Claude Code's checkpointing docs ({claude_checkpointing_doc}) say: "A file that only Bash commands changed isn't tracked and stays as it is." They say subagent edits are usually not captured either. rewindagents records every tool call, copies the project's files before each shell command, and rewinds the files to any step. Claude Code runs the same hooks for a subagent's tool calls, so those are recorded too; that path is tested with payloads shaped the way its hooks docs describe, not yet in a live subagent session.

In the demo session (recorded by a script in the repo), fourteen agent steps run through the hook and the last two are the bad kind: `rm -rf tests`, then an overwritten config file. Two commands show what happened and put the four files back:

```sh
rewindagents replay
rewindagents rewind 12
```

What it is: an open-source recorder (Apache-2.0, Python standard library only). A hook writes every tool call into a hash-chained JSONL log in `.rewindagents/` and copies a project file before an edit or a Bash command changes it (git-ignored files, symlinks, files over 20 MB, projects of more than 20,000 files and, outside git, node_modules, .venv, venv and __pycache__ are the exceptions). `rewindagents replay` lists the steps, `rewindagents rewind 12` puts the files back the way they were right after step 12, and the rewind is itself a step you can undo.

What it is not: it never blocks or changes a call, and it does not send anything anywhere. The hook always exits 0; it prints nothing, except the replies Cursor's hook protocol requires ({"permission": "allow"} before a call, {} after).

Status, plainly: the Claude Code hook has run in real sessions. The Codex and Cursor hooks are built from the vendors' hook docs and tested with the documented payloads, not yet in a live session. Not on PyPI yet; install from the repository with pipx.

Repository: {repo_url}
Docs and the recorded clip: {site_url}

If you try the Codex or Cursor hook and the payload is not what the docs say, an issue with the payload would be the most useful thing you could send.
