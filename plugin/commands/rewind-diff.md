---
description: Show what one recorded step changed, file by file
argument-hint: "<step> [session]"
---

# /rewind-diff

Call the `rewind_diff` MCP tool to see the unified diff for one step.

## What to do

1. Read the step number from `$ARGUMENTS` -- it is required (`step`; 0 means "before the first
   step"). Read an optional `session` too.
2. Call `rewind_diff` with `step` (and `session` if given).
3. By default this tool redacts secrets in every file's unified diff text (`[redacted ...]`).
   Only pass `reveal_secrets: true` when the user explicitly asks to see the raw, unredacted
   text -- that is a deliberate opt-in, never the default, and never something to add on your
   own judgment.
4. Present each changed file's path and change type (`created`, `modified`, `deleted`) with its
   diff.

If the step is out of range for the session, the tool answers `isError: true` naming the step
and the session's real step count -- show that message to the user instead of guessing a
different step number yourself.

This tool is read-only: it writes nothing.
