# Changelog

All notable changes to rewindagents. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the major version is 0, a
minor version may change behaviour; every release is a git tag `vX.Y.Z` that equals `rewindagents.__version__`,
and only a published GitHub release publishes to PyPI (`.github/workflows/publish.yml` refuses a mismatched tag).

## [Unreleased]

### Added
- `blame FILE` / `blame FILE:LINE`: which recorded step wrote each line (or `before` the session, or `by hand`
  after it), with the commands to see that step (`replay --step N --diff`) and take it back alone
  (`revert N`). Rebuilt from the stored copies; a version an `undo` or `rewind` restored keeps its original
  authors. Tests: `tests/test_blame.py`.
- `undo [N]` / `undo --all`: take back the agent's last change (or last N) with no step number to work out.
  It counts only steps that changed a file, from where the files are now, so a repeated `undo` walks back
  through the agent's work instead of undoing the previous undo.
- `redo`: reverse the last `undo`, `rewind` or `rewind-to`.
- `mark NAME`, `marks`, `unmark NAME`, `rewind-to NAME`: named bookmarks in time, kept in
  `.rewindagents/marks.json`.
- `history FILE`: one file's timeline -- each step that created, modified or deleted it.
- `guard PATTERN...`, `guard --check`, `unguard PATTERN`: protected files (`.env`, `secrets/`, `*.pem`). The
  hook still never blocks; on a guarded change Claude Code shows the user a warning (`systemMessage`) and tells
  the agent (`additionalContext`); other agents get it on stderr, their stdout reply unchanged.
- `undo --only FILE` now takes back the agent's last change to that file (it used to count the last change
  overall, then restrict it to the file).
- All of these go through the same rewind checks (a hand edit is refused without `--force`; `--dry-run`).
  Tests: `tests/test_undo.py`, `tests/test_marks.py`, `tests/test_history.py`, `tests/test_guard.py`.

### Changed
- `history` names files relative to the project in each step's summary.

### Fixed
- After an editable install (`pip install -e .`) the next-step hints in `summary`, `revert`, `rewind`, `status`
  and `init` said `python3 -m rewindagents ...`, as if running from a bare clone. Run from a venv that is not
  activated, that command fails with "No module named rewindagents", including the "undo it with" line after a
  revert. They now name the `rewindagents` command pip wrote, found from the install's own `direct_url.json`
  record for this source tree (PEP 610).

## [1.2.0] - 2026-11-18

The full test suite passes on Windows CI, five agent hooks are verified in live sessions on macOS, and Windows
becomes a normal CI row.

No change to the CLI, the exit codes, the hooks or the on-disk format.

### Added
- Live verification of the agent hooks (`harness/live/`, method in `docs/live-verification.md`). On 2026-11-18
  the harness drove each agent's real CLI in a scratch project: the Claude Code (2.1.294), Codex (0.170.0),
  Cursor (2026.11.17-f532c45), Gemini CLI (0.68.0) and Copilot CLI (1.0.114) hooks recorded a real tool call
  before and after, and `rewind 0 --dry-run` printed a restore plan (`VERIFIED_LIVE`). Droid (1.14.0) and Qwen
  Code (0.28.0) ran but, signed in with no model plan or API key, made no tool call (`RAN_NO_LOG`), so they are
  still tested with the documented payloads only. Evidence: `harness/live/evidence/*.json`.
- `tests/live_evidence.py`: the README, `agents.py` and the site's live-status sentences are checked against
  those evidence files in both directions (a `VERIFIED_LIVE` agent must be called verified live, with the
  date, and never "not yet live"; any other agent must be called not yet live and never live).

### Changed
- Windows status: README, docs page, homepage and `CONTRIBUTING.md` no longer say "Windows is not supported".
  They state what is known: the full test suite passes on windows-latest CI (run 44275227200 on `main` at 06a0c0d:
  `Ran 868 tests ... OK (skipped=38)`); the agent hooks were verified in live sessions on macOS, not yet on
  Windows; hook commands under PowerShell are untested (only Git Bash is); and a patch from `diff`,
  `replay --diff` or `compare --diff` saved with `>` on Windows gets CRLF line endings and will not
  `git apply`. The Windows CI job is a normal matrix row now (no `continue-on-error`).
- README, docs page and homepage: the live status per agent follows the evidence, with the setup a user needs:
  Gemini CLI and Copilot CLI run a project's hooks only in a trusted folder; Codex runs a project hook only
  after you review it once (`/hooks`) and loads project config only in a trusted project.
- Harness fixes found in the live run: stdin is closed for the agent (`codex exec` otherwise waits on it);
  Codex runs with `--trust`, `--dangerously-bypass-hook-trust` (the scratch project only) and
  `--skip-git-repo-check`, and `-s workspace-write` in place of the removed `--full-auto`; Gemini CLI runs with
  `GEMINI_CLI_TRUST_WORKSPACE=true` (`--skip-trust` skips project hooks); Copilot CLI runs with
  `--trust-folder`; the hard timeout per agent is 300 s instead of 120 s (Gemini API 503 retries pushed a passing
  run past 120 s).

### Fixed
- Windows: `bundle` recognises every spelling of the project directory the records use (backslashes,
  forward slashes, any letter case, a temp dir's 8.3 short name such as `C:\Users\RUNNER~1`). Before, only
  the resolved path counted, so `import` could leave recorded paths pointing at the source project and a
  later `rewind` wrote there. macOS and Linux spellings are matched exactly as before.
- Windows: the `export` page no longer shows the project's location inside step inputs, where JSON prints
  each `\` of `C:\proj` doubled. The page is written with `\n` line endings on every OS, so the byte count
  `export` reports is the file's size.
- Windows: `rewindagents init` with no input (`< NUL`, a CI job) shows the dry run instead of a `[y/N]` prompt
  that reads end of input as no. `isatty()` is true for the NUL device there; a console handle is now required.
- `init --yes` and `install` remove a stale Copilot hook whichever key it sits under (`bash` or
  `powershell`). A stale Windows-path hook under `bash` was reported replaced but stayed in the file.
- Each of the 87 test failures on windows-latest CI (run 44262918115) has a fix or a skip with a stated
  reason, listed one by one in `docs/windows.md`. The windows-latest job on `main` then passed.

### Security
- VS Code extension dev-only tooling upgraded to clear 17 Dependabot alerts (all development scope):
  vitest 1.6.1 -> 4.1.12 (drops tinypool and esbuild, vite 5.4.21 -> 8.3.8) and `@vscode/vsce` 2.32.0 -> 3.9.2
  (pinned exactly; markdown-it 12.3.2 -> 14.3.3, linkify-it 3.0.3 -> 5.0.2). No test or test config changed.
  The published extension has no runtime dependencies, so the .vsix contents are unaffected.

## [1.1.1] - 2026-11-18

No change to the CLI, the hooks or the on-disk format: this release is about where you can get it.

### Added
- Install routes: Homebrew (`brew install johnbjoseph-cybersec/rewindagents/rewindagents`, tap CI installs and
  tests the formula on macOS and Linux), npm (`npx rewindagents`, a launcher that installs the PyPI release
  into its own virtualenv), and the Claude Code plugin from this repository's own marketplace
  (`claude plugin marketplace add Johnbjoseph-cybersec/rewindagents`, then
  `claude plugin install rewindagents@rewindagents`).
- The VS Code extension is on the VS Code Marketplace as `rewindagents.rewindagents`.
- The site and the docs page list every install route.

### Changed
- The Claude Code plugin has run in a live Claude Code session (2026-11-18): its hook recorded an `rm`, the agent
  called the plugin's MCP tool, and `rewind` put the deleted files back. Evidence:
  `harness/live/evidence/claude-plugin.json`.

## [1.1.0] - 2026-11-18

### Added
- `rewindagents mcp`: a stdio MCP server (JSON-RPC 2.0, standard library only) with seven tools:
  `rewind_sessions`, `rewind_summary`, `rewind_diff`, `rewind_replay`, `rewind_preview` (read only) and
  `rewind_to_step`, `rewind_revert_step` (each needs `confirm: true` and refuses, never retries, where the
  CLI refuses). See `docs/mcp.md`.
- `--json` on `sessions`, `summary`, `diff`, `replay` and `rewind --dry-run`; output without `--json` is
  unchanged. See `docs/json-output.md`.
- A Claude Code plugin at `plugin/`: the MCP server, the hook and five slash commands. Passes
  `claude plugin validate`; not in a marketplace yet, not yet run in a live Claude Code session.
- A VS Code / Cursor extension at `vscode/` over the CLI's `--json` commands, no runtime npm dependencies.
  Not published to a marketplace yet, not yet run in a real VS Code window.
- A Homebrew formula and an npm shim at `packaging/`, both wrappers around the PyPI package; not published.
- `harness/live/`, a harness that drives a real agent in a scratch project and checks the recorded log.
  Run on 2026-11-18: Claude Code verified live; the other six agents were not installed, so their status is
  unchanged (tested with the documented payloads, not live).

### Fixed
- Windows: local fixes for most of the 101 failures the Windows CI job reported; the rest are listed in
  `docs/windows.md`. Windows is still not supported, and the Windows CI job stays experimental until it
  runs green.

## [1.0.0] - 2026-11-18

### Changed
- Stable release. Within 1.x the CLI commands and options documented in the README, the exit codes and the
  on-disk session log, store and bundle format stay compatible; breaking changes come only in 2.0, and a
  deprecation is announced here at least one minor release ahead. See "Stability" in the README.
- PyPI classifier `Development Status :: 5 - Production/Stable` (was `3 - Alpha`).
- README status: "stable" in place of "pre-release"; the limits are unchanged (Claude Code hook live-tested,
  the other six hooks tested with the documented payloads, not live; macOS and Linux only).

### Added
- README section "Stability".

## [0.0.9] - 2026-11-18

### Changed
- Install from PyPI: `pipx install rewindagents` (README, site and launch kit). The PyPI page for 0.0.8 still
  carried the "Not on PyPI yet" README; this release replaces it.
- README and site lead with the shell gap: "Your coding agent ran rm -rf. Take it back.", the demo GIF and a
  comparison with Claude Code's checkpoints on the first screen. Fork and compare is the second section.

### Added
- `CHANGELOG.md`.

## [0.0.8] - 2026-11-18

First release on PyPI.

### Added
- `revert K`: take back one step and keep every later step and hand edit.
- Daily-use CLI: `summary`, `replay N`, `init --agent`, `init --undo`; `status` proves recording by running each
  hook once in a scratch folder.
- The hook keeps a copy of each file as the step left it, not only its hash.
- Failed Claude Code tool calls are recorded.
- takeback-bench, an open benchmark for undoing what a coding agent did.
- PyPI release workflow with Trusted Publishing (no stored token).

### Fixed
- `rewind` puts back git-ignored files and the executable bit.
- Python bytecode is no longer reported as a change.
- A torn write no longer stops the recorder; `gc` frees space after one; `import` accepts a log whose only damage
  is a torn write.
- Windows groundwork: path spellings in bundle import, a nested-lock hang, a hook command form Windows hook shells
  run. Windows is still not supported.
- Hook files are kept out of git (`.git/info/exclude`).

## [0.0.7] - 2026-11-13

Pre-release, GitHub only.

### Added
- `fork` any recorded step and `compare` the runs (files, lines, and your own check).
- Hooks for seven agents: Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, Factory Droid, Qwen Code.

[1.2.0]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v0.0.9...v1.0.0
[0.0.9]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/Johnbjoseph-cybersec/rewindagents/releases/tag/v0.0.7
