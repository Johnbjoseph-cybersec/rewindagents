# rewindagents launch thread for X

Draft for launch day; not posted. One section per post, in order. Fill the addresses with
`python3 brand/launch/fill.py x-thread.md`. tests/test_launch.py counts each post at 280 characters with every
address as 23 (X shortens links). Attach brand/demo.gif to the second post (the recorded session).

## Post 1

Claude Code's own docs: "A file that only Bash commands changed isn't tracked and stays as it is." {claude_checkpointing_doc}

rewindagents takes those back, step by step, from one hash-chained log. Open source, Apache-2.0.

{repo_url}

## Post 2

In this recorded session, the agent's last two steps delete the tests and overwrite the config. One command puts the four files back.

## Post 3

How it works: a hook records every tool call into a hash-chained log, and copies a project file before an edit or a Bash command (sed -i, rm -rf) changes it.

Git-ignored files, symlinks and files over 20 MB are not copied.

## Post 4

rewindagents replay lists the session, one line per step.

rewindagents rewind 12 puts the files back the way they were right after step 12.

The rewind is a step too, so it prints the command that undoes it.

## Post 5

It never blocks or changes a call, and the hook always exits 0 (for Cursor it prints only the replies Cursor requires: allow before a call, {} after).

No server, no network, no dependencies beyond the Python standard library.

## Post 6

Today: Claude Code, tested in real sessions.

Codex and Cursor: built from their hook docs and tested with the documented payloads, not yet in a live session. If you try one, an issue with the real payload helps.

On PyPI: pipx install rewindagents

## Post 7

Install from PyPI with pipx, then run rewindagents install in your project.

Docs and the full clip: {site_url}
