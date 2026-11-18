---
description: Preview what rewinding to a step would do, without changing anything
argument-hint: "<to_step> [session]"
---

# /rewind-preview

Call the `rewind_preview` MCP tool to see the plan for taking the project back to a step -- a
dry run that writes nothing, whatever the plan says.

## What to do

1. Read the target step number from `$ARGUMENTS` -- it is required (`to_step`). Read an
   optional `session` too.
2. Call `rewind_preview` with `to_step` (and `session` if given).
3. Present the plan's `restores` list (which files would be restored, deleted or created) and
   its `drift` list to the user.
4. A non-empty `drift` list means a file changed outside the steps being taken back (by hand,
   by another session, or by a tool with no hook). Say so plainly -- this is information about
   what a real rewind would refuse, not an error from this tool.
5. If the user wants to proceed, point them at `/rewind-to-step` with the same `to_step` --
   this command only previews, it never writes.

This tool is read-only, even on success: it never writes to the project.
