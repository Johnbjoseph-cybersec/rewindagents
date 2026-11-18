---
description: Rewind the project's files back to a recorded step (writes to disk; asks first)
argument-hint: "<to_step> [session]"
---

# /rewind-to-step

Call the `rewind_to_step` MCP tool to take the project's files back to a step. Unlike the other
four commands in this plugin, this one writes to disk.

## What to do

1. Read the target step number from `$ARGUMENTS` -- it is required (`to_step`). Read an
   optional `session` too.
2. First call `rewind_preview` with the same `to_step` (and `session`) and show the user what
   would change: which files would be restored, deleted or created, and whether anything has
   drifted.
3. Ask the user, in their own words, to confirm this is what they want. Do not skip this step,
   and do not treat an earlier message in the conversation as confirmation for a different step
   number.
4. Only after the user confirms, call `rewind_to_step` with `to_step` (and `session`) and
   `confirm: true`. The tool requires `confirm: true` after asking the user -- anything else
   (missing, `false`, or a non-boolean value) answers `isError: true` asking you to get the
   user's go-ahead first and call again with `confirm: true`. There is no stronger confirmation
   and no way to make this tool retry past a refusal.
5. If the call answers `isError: true` with a drift or conflict message (a file changed outside
   the steps being taken back), show the message to the user verbatim. Do not retry with
   different arguments on your own, and do not look for a `force` option -- this tool has none.
   The user can resolve the drift by hand, or use the CLI's own `rewind --force` themselves if
   they choose to accept losing it; this command cannot do that for them.
6. On success, tell the user the step number the rewind itself became, so they know how to take
   it back again later if they need to.
