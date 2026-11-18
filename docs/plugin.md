# The Claude Code plugin

A packaged bundle, at `plugin/`, that wires rewindagents into Claude Code three ways at once: its
own [MCP server](mcp.md) (`rewindagents mcp`, seven tools), the same checkpoint-and-record hook
`rewindagents install --agent claude` writes into a project's `.claude/settings.json`, and five
slash commands that each tell the agent which MCP tool to call for it. None of this is new
behaviour -- the plugin registers the CLI's own hook and the MCP server's own tools; it adds no
logic of its own.

## What is in it

```
plugin/
  .mcp.json                       registers the rewindagents MCP server ("rewindagents mcp")
  .claude-plugin/
    plugin.json                   name, version, description, author
    marketplace.json              a single-plugin marketplace listing, source "./"
  hooks/
    hooks.json                    PreToolUse, PostToolUse, PostToolUseFailure -> `rewindagents
                                   hook --agent claude`, matcher "*"
  commands/
    rewind-status.md              rewind_sessions + rewind_summary
    rewind-replay.md              rewind_replay
    rewind-diff.md                rewind_diff
    rewind-preview.md             rewind_preview (dry run, writes nothing)
    rewind-to-step.md             rewind_to_step -- the only command that writes, and only
                                   after asking the user and setting confirm: true
```

`plugin/.mcp.json` carries exactly the shape `docs/mcp.md`'s Registering-it section documents --
`{"mcpServers": {"rewindagents": {"command": "rewindagents", "args": ["mcp"]}}}` -- which assumes
`rewindagents` is on `PATH` (a pipx, uv tool, or pip install; see the main `README.md`'s Install
section). `plugin/hooks/hooks.json` makes the same assumption for the hook command, so it writes
`rewindagents hook --agent claude` rather than the absolute-interpreter-path form
`rewindagents install` bakes in for one specific machine: a shipped plugin cannot know in advance
whose `sys.executable` it will run under, so it trusts `PATH` the same way `.mcp.json` already
does. From a clone (not installed), follow the clone form in `docs/mcp.md` and `agents.py`
instead of this plugin.

The five commands wrap the MCP tools, nothing else: each one tells the agent which tool to call,
with which arguments, and what to do with the result (`docs/mcp.md` describes the tools
themselves in full, including the redaction rules on `rewind_diff` and `rewind_replay`). Only
`rewind-to-step.md` can change a file; it instructs the agent to call `rewind_preview` first, ask
the user to confirm in their own words, and only then call `rewind_to_step` with `confirm: true`
-- the tool itself requires that exact boolean after the user has been asked, and refuses
(`isError: true`, the `DriftError`/`ConflictError` message verbatim) with no way to retry past
that refusal. `rewind_revert_step` has no slash command in this release; it is reachable only by
asking the agent to call that MCP tool directly.

## PATH trust

Both `plugin/.mcp.json` and `plugin/hooks/hooks.json` spawn the bare command name `rewindagents`,
resolved against whatever `PATH` is in effect at the moment Claude Code starts the MCP server or
runs the hook -- there is no per-install override for this, unlike the VS Code extension's
`rewindagents.cliPath` setting (see `docs/vscode.md`), which lets an install pin an absolute
interpreter path instead of trusting `PATH` resolution. This matters because the resolution
happens twice over, on every tool call: once for the hook (matcher `"*"`, so every single tool
call in the session triggers it) and once for the MCP server covering all seven tools for as long
as the session runs. Anyone installing this plugin should know what `rewindagents` on their own
`PATH` actually resolves to before they do.

A user who wants a fixed interpreter instead of `PATH` resolution can edit the installed plugin
copy's `.mcp.json` and `hooks/hooks.json` directly, replacing the `"rewindagents"` command string
in both files with the absolute path to the intended executable (for example the one a specific
`pipx`, `uv tool`, or venv install produced). That edit lives outside this repository, in the
copy Claude Code's plugin machinery installed; it is not part of the frozen manifest shape this
repo ships and is not re-applied if the plugin is reinstalled or updated.

## Installing it

This repository is its own plugin marketplace (`.claude-plugin/marketplace.json` at the root,
pointing at `plugin/`). From GitHub:

```
claude plugin marketplace add Johnbjoseph-cybersec/rewindagents
claude plugin install rewindagents@rewindagents
```

Inside a Claude Code session the same two steps are `/plugin marketplace add
Johnbjoseph-cybersec/rewindagents` and `/plugin install rewindagents@rewindagents`. From a clone,
pass the clone's path to `marketplace add` instead. `claude plugin install` takes a `--scope`
option (`user`, `project`, or `local`; `user` is the default).

The MCP server it registers needs `rewindagents` on `PATH`: install the package first with
`pipx install rewindagents`, `uv tool install rewindagents`, or `pip install rewindagents` (see
the main `README.md`), then add the marketplace and install the plugin as above.

## Status

Built and validated locally with the Claude Code CLI's own validator
(`claude plugin validate <path>`, run against both `plugin.json` and `marketplace.json` -- see
`tests/test_plugin.py` and the sprint's evidence file for the exact output) and with
`tests/test_plugin.py`, which parses every manifest, derives `hooks.json`'s expected events and
command from `agents.AGENTS["claude"]` at test time, and checks the five command files by name
and content.

It is not in the official Claude Code marketplace; this repository serves as its own marketplace
(above). It has run in a live Claude Code session: on 2026-11-18, Claude Code 2.1.294 with the plugin
loaded (`--plugin-dir plugin`) wrote a file and deleted two files with `rm`; the plugin's hook
recorded all four steps (the `rm` with both files checkpointed), the agent called the plugin's own
`rewind_summary` MCP tool, and `rewindagents rewind 1` afterwards put both deleted files back with
their contents. Install through the marketplace was checked the same day in an empty Claude Code
config directory. Evidence: `harness/live/evidence/claude-plugin.json`.
