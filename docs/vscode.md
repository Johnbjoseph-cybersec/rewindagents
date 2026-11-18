# VS Code extension (`vscode/`)

A per-step session timeline, a readonly diff view, and two commands to look at or take back a
rewind, all driven through the `rewindagents` command line. The extension never reads
`.rewindagents/` files directly and never reimplements diffing, hashing or log logic -- it talks to
one place only, the `rewindagents` CLI, through its `--json` output and two plain action commands.

## What it adds

- **Rewind Timeline** view (Explorer sidebar): every recorded session, and under each session, its
  steps in order (sequence number, tool, files touched). Backed by `rewindagents sessions --json`
  and `rewindagents summary --json`.
- Click a step to open a readonly diff document: what that step itself changed, as the unified
  text `rewindagents diff --json` already produces.
- **Rewind Agents: Preview Rewind** -- runs `rewindagents rewind STEP --dry-run --json` and shows
  the restore plan. If any file changed by hand after the steps being taken back, that is shown as
  a refusal notice instead of a plan, exactly as the CLI itself reports it. Nothing on disk changes
  from a preview.
- **Rewind Agents: Rewind To Here** -- asks for confirmation in a modal dialog first. Only after
  confirming does it run the real `rewindagents rewind STEP`. If the CLI refuses (because
  something changed after the steps being taken back), the refusal is shown as-is. There is no
  force option anywhere in this extension -- `src/cli.ts` has no parameter for one, on any method --
  so a refusal is never retried and never overridden.

`revert` is implemented in `src/cli.ts` (`RewindCli.revert`) and covered by both the fixture-driven
and the real-CLI test suites, but it is not wired to a command, a menu entry, or any `package.json`
contribution yet. That is a scope decision for a later sprint, not an oversight discovered late --
see "What was deliberately not built" below.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `rewindagents.cliPath` | `rewindagents` | Path to the `rewindagents` executable. Set this if it is not on `PATH`. |

## How it talks to the CLI

`src/cli.ts` is the only file that spawns the `rewindagents` binary, and it only ever runs:

```
rewindagents sessions --json
rewindagents summary  --json [--session S]
rewindagents diff     --json STEP [PATH...] [--session S]
rewindagents replay   --json [--step N] [--session S]
rewindagents rewind   STEP --dry-run --json [--session S] [--only PATH]...
rewindagents rewind   STEP [--session S] [--only PATH]...
rewindagents revert   STEP [--session S]
```

`STEP` is a plain positional argument, matching the real CLI's argparse (`rw.add_argument("step",
...)` / `rv.add_argument("step", ...)` in `src/rewindagents/cli.py`) -- there is no `--to` or
`--step` flag on either command. (`replay --step N` above is a real flag; `replay`'s positional
and `--step` name the same thing and either works.)

### The error payload, handled at every parse site

Every `--json` command can print one more shape on a hard failure instead of its usual one -- a
step out of range, an ambiguous session, a log that does not verify
(`src/rewindagents/jsonout.py`'s `error_payload`, documented in `docs/json-output.md`):

```json
{"format": "rewindagents-error", "version": 1, "error": "step 99 is out of range: ..."}
```

`RewindCli`'s single `parseResult` helper is the one place every method's `JSON.parse` result is
checked: a `format` of `'rewindagents-error'` throws a typed `RewindCliError` carrying the CLI's
own `error` message verbatim; a `format` that matches what the method asked for returns the typed
value; anything else (an unexpected shape, or stdout that was not JSON at all) throws a plain
`Error` naming what was expected instead. No method ever mis-casts an error object as a success
shape -- the defect this closes was exactly that: `previewRewind()` reading `plan.restores.length`
off an object with no `restores` field, and crashing.

`timelineModel.ts` (`loadSessionNodes`, `loadStepNodes`) and `rewindActions.ts`
(`previewRewind`) catch `RewindCliError` and report it through an injected `showError`/`notify`
seam -- a plain `(message: string) => void` function, the same shape `ConfirmFn` already used for
the confirm-before-rewind modal -- instead of letting it reach VS Code as an unhandled rejection.
In tests that seam is a `vi.fn()`; in the real extension (`extension.ts`) it is wired to
`vscode.window.showErrorMessage`. `extension.ts`'s diff content provider catches the same error
around its own `cli.diff()` call and renders the message as the document's own text, since a
readonly document provider has no modal of its own to raise a popup from.

### Process launch is injected

The process launch itself is injected (`ExecFn`), so most tests in this package run against
fixture JSON under `tests/fixtures/` instead of a real binary. `tests/cli.real-cli.test.ts` is the
one file that does not mock it: it spawns the actual `rewindagents` CLI from this repo's
`src/rewindagents` (via `PYTHONPATH`, skipped if no `python3`/`python` is on `PATH`).

## Development

```
npm ci
npm run compile   # tsc -> out/
npm test          # vitest; fixture-driven tests plus the real-CLI suite (needs python3, no VS Code)
npm run package   # mkdir -p dist && vsce package --out dist/ -> dist/rewindagents-0.0.1.vsix
```

### Packaging quirk recorded for whoever runs this next

`@vscode/vsce@2.32.0` (pinned exactly in `devDependencies`, not a caret range) with
`--out dist/` and no pre-existing `dist/` directory writes a file literally named `dist`
(not `dist/<name>.vsix`), then fails with `ENOTDIR: not a directory, stat 'dist/'` on its own
final step. Reproduced by hand, twice, from a directory with no `dist/` anything -- not an
environment fluke. The `package` script therefore runs `mkdir -p dist &&` first; running the bare
`npx vsce package --out dist/` without that directory already existing reproduces the failure.

## Project layout

```
vscode/
  package.json          extension manifest (publisher: rewindagents)
  LICENSE                Apache-2.0, identical to the repo root's
  .vscodeignore          keeps src/, tests/, tsconfig.json, vitest.config.ts, *.map out of the .vsix
  tsconfig.json
  src/
    cli.ts               the one CLI adapter; injectable exec; RewindCliError; every parse site guarded
    types.ts             the five frozen --json success shapes, plus ErrorResult
    diffFormat.ts         renders a diff --json result as plain text
    timelineModel.ts      pure session/step -> tree node transforms, plus CLI-calling loadSessionNodes/loadStepNodes
    rewindActions.ts      preview + confirm-then-rewind, vscode-free, catches RewindCliError
    extension.ts           wires the above into TreeView, commands, settings, a real vscode.window.showErrorMessage seam
  tests/
    fixtures/*.json       one fixture per frozen JSON shape, plus error.json
    *.test.ts
    cli.real-cli.test.ts  spawns the real CLI: positional-argv regression suite, plus a full
                           timeline -> diff -> preview -> rewind -> drift-refusal -> error-path run
  dist/
    rewindagents-0.0.1.vsix   built artifact; gitignored (*.vsix), produced by `npm run package`
```

## Honest status

- **Published** on the VS Code Marketplace as `rewindagents.rewindagents` 1.1.0 (publisher
  `rewindagents`, 2026-11-18). Checked the same day: `code --extensions-dir <empty dir>
  --install-extension rewindagents.rewindagents` installed `rewindagents.rewindagents@1.1.0` from the
  Marketplace, and the item page answered 200. Not yet on Open VSX. `npm run package` builds
  `vscode/dist/rewindagents-<version>.vsix`.
- **Not yet tested inside a live VS Code host.** Every test in `tests/` runs under `vitest` in
  plain Node, against either a mocked `exec` or (in `cli.real-cli.test.ts`) the real
  `rewindagents` CLI spawned as a child process -- none of them load the `vscode` module or launch
  an Extension Development Host. What they prove, precisely:
  - `cli.test.ts`, `rewindActions.test.ts`, `timelineModel.test.ts`, `diffFormat.test.ts`: the
    adapter builds the exact argv the CLI's argparse accepts (per the real-CLI suite's own
    regression-control case), parses all five frozen success shapes plus the error shape
    correctly, never appends a force option, and the pure preview/confirm/tree-node/diff-text
    logic behaves correctly against fixture JSON -- including every `RewindCliError` path.
  - `cli.real-cli.test.ts`: against a real, hook-checkpointed two-step session recorded through
    `python3 -m rewindagents hook` (the same entry point Claude Code's own hook runner calls, with
    the payload shape `tests/test_hook.py` in the Python suite documents), `sessions()`,
    `summary()`, `diff()`, `replay()`, `rewindDryRun()` and `rewind()` all run against the actual
    CLI binary from this repo's source and are checked against what it actually printed and
    actually wrote to disk -- including `rewind()` restoring real file bytes, a drift case where a
    hand edit outside any recorded step makes the CLI refuse and the file stays untouched, and an
    out-of-range step on `diff()` raising `RewindCliError` with the CLI's own message.
  - None of this exercises VS Code's own TreeView rendering, modal dialogs, `TextDocumentContentProvider`
    registration, or the `.vsix`'s install/activation path inside an actual editor window. The
    `.vsix` has been packaged and its contents inspected (`unzip -l`), not installed into a running
    VS Code and clicked through.
