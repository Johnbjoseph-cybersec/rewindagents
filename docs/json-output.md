# `--json`: five shapes, read from the same engine as the text output

`sessions`, `summary`, `diff` and `replay` take a plain `--json` flag; `rewind` takes `--dry-run
--json` (there is no way to print a real, writing rewind as JSON from the CLI -- see
[`docs/mcp.md`](mcp.md)'s `rewind_to_step` for that, which needs `confirm:true` instead). All five
are additive: every existing option on these commands works exactly as before, the human-readable
output when `--json` is not given is unchanged byte for byte, and every exit code these commands
already used still means the same thing. `--json` never implies or enables `--force`.

With `--json`, **stdout carries exactly one JSON object and nothing else.** Anything a command
already printed to stderr (a `CANNOT`, a drift warning, a note about an unfinished scan) still goes
to stderr, unchanged, so a script that only reads stdout never has to skip over it.

All five shapes, and the functions that build them, live in `src/rewindagents/jsonout.py`. It reads
the log the same way the text commands do -- through `rewind.py`, `diff.py`, `sessions.py` and
`log.py` -- so the JSON and the text can never disagree about what happened; `summary.py` and
`diff.py` themselves are never edited to produce these shapes.

## sessions

```
rewindagents sessions --json [--grep TEXT]
```

```json
{"format": "rewindagents-sessions", "version": 1,
 "sessions": [{"session": "s1", "steps": 2, "first_ts": "2026-11-17T20:30:55.784Z",
               "last_ts": "2026-11-17T20:30:55.785Z"}]}
```

One entry per session, in the order `sessions` (without `--json`) already lists them. `--grep`
filters the same way it does for the text output; with no match, exit code 1 (as without `--json`),
and `"sessions": []` on stdout rather than the usual stderr message.

## summary

```
rewindagents summary --json [--session ID]
```

```json
{"format": "rewindagents-summary", "version": 1, "session": "s1",
 "steps": [{"seq": 1, "ts": "2026-11-17T20:30:55.784Z", "actor": "agent", "event": "pre",
            "tool": "Write", "files": ["app.py"]}, ...]}
```

Every step of the session, in order: `seq` is the record's own sequence number in the log (unique
and increasing across the whole log, not just this session -- the same number `replay`'s `--step`
and `diff`'s step argument use, and what `rewind_replay`'s `from_seq`/`to_seq` filter on),
`event` is `"pre"` for an ordinary tool call or the event name of a rewind/branch/revert/fork step,
`files` is the project-relative paths the step checkpointed (created, changed or deleted; empty for
a step that touched nothing, such as a plain read). Note that this is a per-step listing, not the
net-change-per-file view the human `summary` command prints (that view, and its "take it back"
command suggestions, has no JSON shape of its own; `replay --json` with no step is the closest
machine-readable equivalent of "what did this session do").

## diff

```
rewindagents diff --json STEP [PATH ...] [--session ID]
```

```json
{"format": "rewindagents-diff", "version": 1, "session": "s1", "step": 1,
 "files": [{"path": "app.py", "change": "modified",
            "unified": "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-v2\n...\n+v1\n...\n"}]}
```

What `rewind STEP` would change, one entry per file, in the same order the plain `diff` command
already prints them (restores, then deletes). `change` is `"created"` when the file does not exist
now and this step would bring it back, `"modified"` when it exists now and would change, `"deleted"`
when it exists now and this step would remove it. `unified` is the exact text `diff` (without
`--json`) writes to stdout for that file -- **never redacted**, under `--json` or not: `diff` has no
`--no-redact` flag at all, unlike `replay`, `export` and `bundle`, and `--json` does not add one.
This is the CLI's own default, and `jsonout.diff_payload`'s own default (`redact_secrets=False`),
unchanged by this sprint. The MCP `rewind_diff` tool wraps this same function but is a different
caller with a different default: it passes `redact_secrets=True` unless its own call asks for
`reveal_secrets: true` -- see [`docs/mcp.md`](mcp.md). Nothing here, and nothing `diff` or
`diff --json` print, changes because of that.

Exit code: the same one `diff` already returns for this plan (1 when something could not be shown,
an unfinished scan, or a file drifted since; 2 for a step number this session does not have; 0
otherwise) -- `jsonout.diff_exit_code` is the one place that rule is written, read by both this flag
and `diff.run`'s own ordinary path.

## replay

```
rewindagents replay --json [N | --step N] [--session ID] [--no-redact]
```

```json
{"format": "rewindagents-replay", "version": 1, "session": "s1",
 "steps": [{"seq": 1, "ts": "2026-11-17T20:30:55.784Z", "actor": "agent", "event": "pre",
            "tool": "Write", "files": ["app.py"], "result": "{\"ok\": true}"}, ...]}
```

The same per-step rows as `summary --json`, plus `result`: the step's own recorded result, always a
JSON **string** (via `json.dumps`, so a result that is itself a dict, a list or `null` still comes
back as one predictable type, never three). With no step named, every step of the session is
listed, as plain `replay` lists them; naming one (`replay N --json` or `replay --step N --json`)
narrows the list to that step alone. `--diff` is not supported together with `--json` (a step's
diff has its own shape -- `diff --json`); the combination is a usage error, exit 2, same as any
other option this command cannot use together.

Secrets in `result` are replaced (`[redacted ...]`) by default, exactly as plain `replay` already
does; `--no-redact` keeps them, exactly as it already does. This is the one shape here where
`--json` changes *content*, not just format, from the default -- because without it, a result like
a `cat .env` output would otherwise land in a script's stdout the same way it would land in a
terminal.

## rewind --dry-run --json

```
rewindagents rewind STEP --dry-run --json [--session ID] [--only PATH] [--force]
```

```json
{"format": "rewindagents-rewind-plan", "version": 1, "session": "s1", "to": 1,
 "restores": [{"path": "app.py", "action": "restore"}],
 "drift": []}
```

`restores` lists every file the rewind would touch, in the same restore-then-delete order the
human `--dry-run` output already prints them, each with the action that file would get:
`"restore"` (it exists now, its bytes would change), `"create"` (it does not exist now, this step
had it), or `"delete"` (it exists now, this step did not). `drift` lists, for files this rewind
would overwrite, every one that changed outside the steps being taken back -- same files, same
`reason` text `rewind --dry-run` already prints on a WARNING line -- information for a dry run,
not a reason this call itself fails.

`--json` on `rewind` needs `--dry-run`: there is no way to print a real, writing rewind as JSON on
the CLI. Asking for `--json` without `--dry-run` is a usage error, exit 2, and changes nothing --
for a confirmed, real rewind printed this way, see the `rewind_to_step` MCP tool in
[`docs/mcp.md`](mcp.md), which needs `confirm:true` in place of a CLI flag.

Exit code: 0 when `drift` is empty (or `--force` was given, since a real `--force` rewind would
proceed despite it); 1 when it is non-empty and `--force` was not given (a real rewind would
refuse), or when the plan could not restore everything (`cannot`, an unfinished scan, a torn
write) -- the exact rule a real `rewind --dry-run` already uses, in one place
(`jsonout.rewind_dry_run_exit_code`), read by both. The plan is still printed either way.

## On a hard failure

A step number the session does not have, an unknown or ambiguous `--session`, or a log that does
not verify: the same exit code the command already used (2 for an out-of-range step, 1 for most
other failures), and on stdout, in place of the shape above, one object:

```json
{"format": "rewindagents-error", "version": 1, "error": "step 99 is out of range: session s1 has 2 steps, so use 1-2; `replay` lists them"}
```

An unknown `--session` is resolved (and, on failure, reported) before any `--json` code runs at
all -- the same `SessionError` every other command already raises for it, printed to stderr with
exit 1 as it always was, never wrapped as JSON.
