---
description: Replay a rewindagents session's recorded steps, in order
argument-hint: "[from_seq] [to_seq] [session]"
---

# /rewind-replay

Call the `rewind_replay` MCP tool to walk back through what a session's steps actually did.

## What to do

1. Read `$ARGUMENTS` for an optional `from_seq`, `to_seq` and `session`. All three are optional
   -- leaving them out replays the whole current session.
2. Call `rewind_replay` with whichever of `from_seq`, `to_seq`, `session` the user gave.
3. The result's `steps` list already has secrets in each step's `result` replaced with
   `[redacted ...]` -- this tool has no argument to turn that off. Present each step's sequence
   number, actor, event, tool, files and result, in order.
4. If the user asks for the raw, unredacted result of a specific step, point them at
   `/rewind-diff` with `reveal_secrets: true` instead -- `rewind_replay` cannot give it to them.

This tool is read-only: it changes nothing on disk.
