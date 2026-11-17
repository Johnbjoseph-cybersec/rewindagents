# Changelog

All notable changes to rewindagents. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the major version is 0, a
minor version may change behaviour; every release is a git tag `vX.Y.Z` that equals `rewindagents.__version__`,
and only a published GitHub release publishes to PyPI (`.github/workflows/publish.yml` refuses a mismatched tag).

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

[1.0.0]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v0.0.9...v1.0.0
[0.0.9]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/Johnbjoseph-cybersec/rewindagents/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/Johnbjoseph-cybersec/rewindagents/releases/tag/v0.0.7
