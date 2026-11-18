# rewindagents for VS Code and Cursor

A per-step timeline for what your coding agent did, a readonly diff per
step, and two commands to look at or take back a rewind, all driven
through the `rewindagents` command line.

This extension never reads `.rewindagents/` files directly and never
reimplements diffing, hashing or log logic. It talks to one place only:
the `rewindagents` CLI, through its `--json` output.

## Getting started

1. Install the `rewindagents` CLI (macOS or Linux, Python 3.10+), any one of:
   `pipx install rewindagents`, `brew install johnbjoseph-cybersec/rewindagents/rewindagents`, or `npx rewindagents`.
2. In your project, add the hook for the coding agents you use: `rewindagents init`.
3. Let the agent work. Open the **Rewind Timeline** view in the Explorer sidebar to see every step, click a
   step for its diff, and use **Preview Rewind** or **Rewind To Here** to take steps back.

If `rewindagents` is not on the `PATH` VS Code sees, set `rewindagents.cliPath` to its full path.
More: https://github.com/Johnbjoseph-cybersec/rewindagents

## What it adds

- **Rewind Timeline** view (Explorer sidebar): every recorded session,
  and under each session, its steps in order (sequence number, tool,
  files touched).
- Click a step to open a readonly diff document: what that step itself
  changed, as the unified text the CLI already produces.
- **Rewind Agents: Preview Rewind** - runs a dry run and shows the
  restore plan. If any file changed by hand after the steps being taken
  back, that is shown as a refusal notice instead of a plan, exactly as
  the CLI itself reports it. Nothing on disk changes from a preview.
- **Rewind Agents: Rewind To Here** - asks for confirmation in a modal
  dialog first. Only after you confirm does it run the real rewind. If
  the CLI refuses (because something changed after the steps being
  taken back), the refusal is shown as-is. There is no force option
  anywhere in this extension; a refusal is never retried or overridden.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `rewindagents.cliPath` | `rewindagents` | Path to the `rewindagents` executable. Set this if it is not on `PATH`. |

## How it talks to the CLI

`src/cli.ts` is the only file that spawns the `rewindagents` binary, and
it only ever runs:

```
rewindagents sessions --json
rewindagents summary  --json [--session S]
rewindagents diff     --json STEP [PATH...] [--session S]
rewindagents replay   --json [--step N] [--session S]
rewindagents rewind   STEP --dry-run --json [--session S]
rewindagents rewind   STEP [--session S]
rewindagents revert   STEP [--session S]
```

`STEP` is a plain positional argument, matching the real CLI's argparse
(`rw.add_argument("step", ...)` / `rv.add_argument("step", ...)` in
`src/rewindagents/cli.py`) -- there is no `--to` or `--step` flag on
either command. (`replay --step N` above is a real flag; `replay`'s
positional and `--step` name the same thing and either works.)

Every `--json` command can also print the `rewindagents-error` shape on a hard failure (a step out
of range, an ambiguous session, a log that does not verify). `RewindCli` checks the parsed
`format` field on every call: that shape throws a typed `RewindCliError` carrying the CLI's own
message, the shape a method actually asked for is returned normally, and anything else throws a
plain `Error` naming what was unexpected. `rewindActions.ts` and `timelineModel.ts` catch
`RewindCliError` and report it through an injected `showError` seam (same shape as the existing
`ConfirmFn`), so a failure reaches the user as one message instead of an unhandled rejection. See
[`docs/vscode.md`](https://github.com/Johnbjoseph-cybersec/rewindagents/blob/main/docs/vscode.md) for the full writeup, including the honest status of what is
and is not tested.

The process launch itself is injected (`ExecFn`), so most tests in this
package run against fixture JSON under `tests/fixtures/` instead of a
real binary. `tests/cli.real-cli.test.ts` is the one exception: it spawns
the actual `rewindagents` CLI from this repo's `src/rewindagents` (via
`PYTHONPATH`, skipped if no `python3`/`python` is on `PATH`), both for the
positional-argv regression checks and for a full timeline -> diff ->
preview -> rewind run against a real, hook-checkpointed session, including
a drift-refusal case and an out-of-range-step error case. `npm run compile`
type-checks the extension against the real `vscode` API; it does not
require the `rewindagents` CLI to be installed.

## Development

```
npm ci
npm run compile   # tsc -> out/
npm test          # vitest; fixture-driven tests plus the real-CLI suite (needs python3, no VS Code)
npm run package   # mkdir -p dist && vsce package --out dist/ -> dist/rewindagents-<version>.vsix
```

`npm run package` pre-creates `dist/` itself: `@vscode/vsce@3.9.2` (pinned exactly) writes a
file literally named `dist` instead of `dist/<name>.vsix` and then fails if that directory does
not already exist when `--out dist/` is given -- see [`docs/vscode.md`](https://github.com/Johnbjoseph-cybersec/rewindagents/blob/main/docs/vscode.md).

## Project layout

```
vscode/
  package.json          extension manifest (publisher: rewindagents)
  LICENSE                Apache-2.0, identical to the repo root's (vsce requires one in-folder)
  .vscodeignore          keeps src/, tests/, tsconfig.json, vitest.config.ts, *.map out of the .vsix
  tsconfig.json
  src/
    cli.ts               the one CLI adapter; injectable exec; RewindCliError; every parse site guarded
    types.ts             the five frozen --json success shapes, plus ErrorResult
    diffFormat.ts         renders a diff --json result as plain text
    timelineModel.ts      pure session/step -> tree node transforms, plus CLI-calling loadSessionNodes/loadStepNodes
    rewindActions.ts      preview + confirm-then-rewind, vscode-free, catches RewindCliError
    extension.ts           wires the above into TreeView, commands, settings, a real showErrorMessage seam
  tests/
    fixtures/*.json       one fixture per frozen JSON shape, plus error.json
    *.test.ts
    cli.real-cli.test.ts  spawns the real CLI: positional-argv regression suite, plus a full
                           timeline -> diff -> preview -> rewind -> drift-refusal -> error-path run
  dist/
    rewindagents-0.0.1.vsix   built artifact; gitignored (*.vsix), produced by `npm run package`
```
