---
description: Show this project's rewindagents sessions and a summary of the current one
argument-hint: "[session]"
---

# /rewind-status

Report what rewindagents has recorded for this project, through its MCP server.

## What to do

1. Call the `rewind_sessions` MCP tool (no arguments). It lists every session rewindagents
   knows about here, each with its step count and first/last timestamp.
2. Call the `rewind_summary` MCP tool. Pass `session` only if the user named one in
   `$ARGUMENTS`; otherwise call it with no arguments, and it answers for the session that wrote
   the log's last record.
3. Present both results in plain language: how many sessions exist, which one is current, and
   its steps in order (sequence number, actor, event, tool, files touched).

If `rewind_sessions` comes back with an empty list, say the log is empty and stop there --
`rewind_summary` has nothing to answer for a project with no recorded sessions.

Both tools are read-only: neither one writes to the project or to the log.
