# `rewindagents mcp`

A Model Context Protocol server for rewindagents, reached over its own stdin and stdout. It is a
thin read/write layer over the same engine the CLI uses (`rewind.py`, `revert.py`, `summary.py`,
`diff.py`, `sessions.py`, `log.py`): nothing here re-implements rewinding, reverting, diffing or
listing sessions, and nothing here is reachable except through the seven tools below.

Python standard library only -- `json` and `sys` for the protocol, plus rewindagents' own modules.
No extra dependency, no network, no account: the same promise the rest of rewindagents makes.

## Starting it

```
rewindagents mcp
```

It reads one JSON-RPC 2.0 message per line from stdin, writes one per line to stdout, and keeps
going until stdin ends (then it exits 0). There is no `--log` option on `mcp`: a tool call reads
whichever project the server's current working directory belongs to, worked out the same way the
CLI does with no `--log` of its own (this directory's `.rewindagents/`, or the nearest parent's).
Run it with the working directory set to the project you want it to serve -- an MCP client that
spawns a server per project already does this.

### Registering it

Any MCP client that can run a local stdio command can use it. The general shape:

```json
{
  "mcpServers": {
    "rewindagents": {
      "command": "rewindagents",
      "args": ["mcp"]
    }
  }
}
```

For Claude Code specifically, the plugin at `plugin/.mcp.json` carries exactly this. If
`rewindagents` is not on PATH (a clone, not installed with pipx), use the same form the CLI's own
`install`/`hook` commands use for that agent (`python3 -m rewindagents mcp` with `PYTHONPATH` set
to the clone's `src/`, or the equivalent `python <clone>/src/rewindagents/__main__.py mcp` on
Windows -- see `agents.py` and `README.md`'s install section).

## The protocol

Newline-delimited JSON-RPC 2.0. `protocolVersion` is `"2025-06-18"`; `initialize` echoes it back
when the client asked for that exact version, and answers with `"2025-06-18"` for any other value
(including none) -- there being only the one version this server knows.

| method | what it does |
|---|---|
| `initialize` | handshake; returns `protocolVersion`, `capabilities`, `serverInfo` |
| `notifications/initialized` | acknowledged by convention; no reply is sent, as for any `notifications/...` method |
| `ping` | returns `{}` |
| `tools/list` | returns the seven tools below |
| `tools/call` | `{"name": ..., "arguments": {...}}`; returns `{"content": [...], "isError": bool}` |

Anything else: a method the server does not recognise answers `-32601` (method not found); a line
that is not valid JSON answers `-32700` (parse error), with `id: null` since the id, if any, could
not be read. Both answers leave the server running -- one bad line never ends the session for the
calls after it. A request with no `id` is a notification: by JSON-RPC convention it gets no reply
at all, whether or not the server recognises its method.

`serverInfo.version` is read from the installed package's own `__version__` (never hand-written
here), so it always matches what `rewindagents --version` prints.

## The seven tools

Five read-only, two destructive. None of the seven takes a `force` argument, on either side: the
destructive pair's own safety is "ask again with `confirm:true`", never "ask again, harder".

| tool | arguments | hint |
|---|---|---|
| `rewind_sessions` | *(none)* | read-only |
| `rewind_summary` | `session?` | read-only |
| `rewind_diff` | `step` (required), `session?`, `reveal_secrets?` | read-only |
| `rewind_replay` | `from_seq?`, `to_seq?`, `session?` | read-only |
| `rewind_preview` | `to_step` (required), `session?` | read-only |
| `rewind_to_step` | `to_step` (required), `session?`, `confirm` (required) | destructive |
| `rewind_revert_step` | `step` (required), `session?`, `confirm` (required) | destructive |

`session` is always optional and always means the same thing it means on the CLI: the id of a
session, or a unique prefix of one (the same lookup `rewindagents replay --session ...` uses);
left out, it is the session that wrote the log's last record. Every `session` the caller supplies
is checked this way before anything else runs, so an unknown or ambiguous id comes back as a clear
`isError: true` naming the sessions that are there, never a silent fall-through to "the latest".

### The five read-only tools

Each wraps the matching shape from [`docs/json-output.md`](json-output.md) -- the very same JSON
the CLI's `--json` flag prints for `sessions`, `summary`, `diff` and `replay` -- as the single text
content of the result. A caller that already knows those shapes from the CLI already knows what
these tools return.

- `rewind_sessions` -> `rewindagents-sessions`
- `rewind_summary` -> `rewindagents-summary`
- `rewind_diff` -> `rewindagents-diff`, with secrets in every file's `unified` text replaced
  (`[redacted ...]`) **by default**. This is the one place this tool's default differs from the
  plain CLI: `diff` (and `diff --json`, see json-output.md) has never been redacted at all, because
  the only audience for a human's own terminal is that human. This server's audience is different --
  in practice an MCP client is an AI coding agent backed by a cloud LLM, and whatever this tool
  returns becomes that model's own context, the same exposure `rewind_replay` already guards against
  below. Pass `reveal_secrets: true` in the call's arguments to get the raw, unredacted text back; it
  is a deliberate, explicit opt-in (not a default, and not the same thing as the CLI's own default),
  so a caller has to ask for the dangerous behavior by name.
- `rewind_replay` -> `rewindagents-replay`, **always** with secrets in each step's `result`
  replaced (`[redacted ...]`). The CLI's `replay --json` defaults to the same redaction but can be
  asked not to with `--no-redact`; this tool has no such argument, so there is no way to ask it for
  the raw bytes -- on purpose, since a result from this tool is as likely to end up in a chat
  transcript as a log file.
- `rewind_preview` -> `rewindagents-rewind-plan` (the same shape `rewind --dry-run --json` prints).
  It writes nothing, whatever the plan says: a non-empty `drift` array here is information, not a
  reason the tool call itself fails.

`rewind_diff` and `rewind_preview` take a step number (0 = before the first step, as everywhere
else); a step your session does not have answers `isError: true` with the same "step N is out of
range, session S has M steps" wording every CLI command already uses.

### The two destructive tools

```json
{"name": "rewind_to_step", "arguments": {"to_step": 3, "confirm": true}}
{"name": "rewind_revert_step", "arguments": {"step": 2, "confirm": true}}
```

`confirm` must be the JSON boolean `true` -- not `"true"`, not `1`, not merely truthy, and not
missing. Anything else answers `isError: true`, asking the caller to get the user's go-ahead and
call again with `confirm: true`; nothing is written, and nothing is read beyond working out that
message. This is the only gate: there is no second, stronger confirmation and no `force` argument
to hand it on this tool's behalf.

Once confirmed, the call runs for real (`rewind.rewind(..., dry_run=False)` /
`revert.revert(..., dry_run=False)`), under exactly the same refusal rules the CLI's `rewind` and
`revert` commands already enforce:

- `rewind_to_step` raises `DriftError` when a file it would restore or delete changed outside the
  steps being taken back (by hand, by another session, or by a tool with no hook). That message --
  which files, and by whom -- reaches the caller **verbatim** as `isError: true`. The tool never
  retries with a force it does not have; asking again with the same arguments refuses the same way,
  every time, until the drift is dealt with by hand or the caller accepts losing it through the CLI
  (`rewind N --force`, which this tool cannot do for you).
- `rewind_revert_step` raises `ConflictError` when the step's own change and a later change touch
  the same lines (or disagree about a create or a delete). Same rule: the message reaches the
  caller verbatim, nothing is written, and the tool never retries.

On success, `rewind_to_step` answers with the `rewindagents-rewind-plan` shape plus one extra field,
`record` -- the step number the rewind itself became (so it can be taken back with
`rewind_to_step` again, or `rewindagents rewind <record - 1>` on the CLI). `rewind_revert_step`
answers with its own shape (not one of the CLI's five, since `revert` has no `--json` flag):

```json
{
  "format": "rewindagents-revert-result", "version": 1,
  "session": "...", "step": 2,
  "write": ["path", ...], "delete": ["path", ...], "same": ["path", ...], "merged": ["path", ...],
  "cannot": [{"path": "...", "why": "..."}],
  "record": 7
}
```

`write`/`delete`/`same`/`merged` are project-relative paths (`merged` is the subset of `write` whose
bytes are a three-way merge, not simply the file as it was before the step); `cannot` lists, with
why, any file the revert could not touch (outside the project, a symlink where the file was, a scan
that never finished); `record` is the revert's own step number.

## Project state the server can see

With no `.rewindagents/log.jsonl` at all in the project (no hook has ever run, or `rewindagents
init` was never run), every tool answers `isError: true` with a message saying so, rather than a
confusing shape built from nothing. `rewind_sessions`/`rewind_summary` with a log that genuinely
holds zero sessions (the file exists, nothing is in it yet) answer normally with empty lists; that
is a different, legitimate state from "there is no log".

## A worked example

```
-> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}
<- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},
                                     "serverInfo":{"name":"rewindagents","version":"1.0.0"}}}
-> {"jsonrpc":"2.0","method":"notifications/initialized"}
   (no reply)
-> {"jsonrpc":"2.0","id":2,"method":"tools/list"}
<- {"jsonrpc":"2.0","id":2,"result":{"tools":[... 7 tools ...]}}
-> {"jsonrpc":"2.0","id":3,"method":"tools/call",
    "params":{"name":"rewind_summary","arguments":{}}}
<- {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":
      "{\"format\": \"rewindagents-summary\", \"version\": 1, \"session\": \"s1\", \"steps\": [
        {\"seq\": 1, \"ts\": \"2026-11-17T20:53:16.251Z\", \"actor\": \"agent\", \"event\": \"pre\",
         \"tool\": \"Write\", \"files\": [\"app.py\"]},
        {\"seq\": 3, \"ts\": \"2026-11-17T20:53:16.252Z\", \"actor\": \"agent\", \"event\": \"pre\",
         \"tool\": \"Write\", \"files\": [\"app.py\"]}]}"
   }],"isError":false}}
-> {"jsonrpc":"2.0","id":4,"method":"tools/call",
    "params":{"name":"rewind_to_step","arguments":{"to_step":1}}}
<- {"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text","text":
      "rewind_to_step requires confirmation: ask the user before putting this project's files back to
       step 1, then call again with confirm set to true"
   }],"isError":true}}
-> {"jsonrpc":"2.0","id":5,"method":"tools/call",
    "params":{"name":"rewind_to_step","arguments":{"to_step":1,"confirm":true}}}
<- {"jsonrpc":"2.0","id":5,"result":{"content":[{"type":"text","text":
      "{\"format\": \"rewindagents-rewind-plan\", \"version\": 1, \"session\": \"s1\", \"to\": 1,
        \"restores\": [{\"path\": \"app.py\", \"action\": \"restore\"}], \"drift\": [], \"record\": 5}"
   }],"isError":false}}
```

(wrapped for the page; on the wire each of the above is one line. This is a real, two-step session
-- `write app.py "v1"` then `write app.py "v2"` -- replayed through the real server; nothing here is
invented.)

## Why `mcp.py` reads `jsonout.py` instead of its own copy of the shapes

`cli.py`'s `--json` flags and this server both call the same functions in `jsonout.py`. That module
reads the log through `rewind.py`, `diff.py`, `sessions.py` and `summary.py` -- the same functions
the human-readable commands use -- so a session, a diff or a rewind plan cannot read one way from
the CLI and a different way from an agent talking to this server. Only the Python API of
`rewind.py`/`diff.py`/`revert.py`/`sessions.py` is not part of rewindagents' own stability promise
(see README.md's Stability section); the CLI surface and this server's seven tool schemas are the
two things promised stable going forward.
