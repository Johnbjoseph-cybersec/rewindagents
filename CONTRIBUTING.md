# Contributing to rewindagents

## Branches

`main` is protected: every change reaches it through a pull request, and the Linux and macOS test jobs must
pass first. Nobody pushes to `main` directly, maintainers included.

| Branch | For | Example |
|---|---|---|
| `feat/<topic>` | a new feature or capability | `feat/live-agent-hooks` |
| `fix/<topic>` | a bug fix | `fix/windows-ci` |
| `docs/<topic>` | documentation only | `docs/branching` |
| `chore/<topic>` | tooling, dependencies, CI | `chore/vscode-dev-deps` |

1. Branch from the latest `main`: `git switch -c fix/<topic> origin/main`.
2. Keep one change per branch. Write commit messages that say what changed and why.
3. Run the suite before you push: `PYTHONPATH=src python3 -m unittest discover -s tests`.
4. Push the branch and open a pull request against `main`. CI runs on Linux, macOS and Windows.
5. Merge when the required checks are green. Delete the branch after the merge.

The Windows job does not block a merge yet: Windows is not supported until that job is green (see
`docs/windows.md`).

## Releases

Releases are cut from `main` only, after the change is merged:

1. Bump `src/rewindagents/__init__.py` and move the `## [Unreleased]` notes in `CHANGELOG.md` under the new version
   (Semantic Versioning: within 1.x the CLI, exit codes and on-disk format stay compatible).
2. Merge that through a pull request like any other change.
3. Create the GitHub release `vX.Y.Z` on `main`. Publishing the release uploads the package to PyPI
   (`.github/workflows/publish.yml` refuses a tag that does not match the package version).

## What a change must keep

- Python standard library only in the package.
- No claim in the README or site without evidence on disk; tests pin the wording to the code and to
  `harness/live/evidence/`.
- macOS and Linux behaviour, CLI options, exit codes and the on-disk log, store and bundle format stay compatible
  within 1.x.

## Reporting a problem

Open an issue with the command you ran and what happened. For a hook problem, `rewindagents replay --step N`
prints what was recorded for that step.
