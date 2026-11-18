# Install channels

rewindagents ships on PyPI today (`pipx install rewindagents`, `pip install
rewindagents`, `uv tool install rewindagents` — see the main `README.md`
Install section for the authoritative commands). This file covers the two
additional channels added under `packaging/`: Homebrew and npm. Both are thin
wrappers around the same PyPI package; neither duplicates its logic.

## Homebrew

Files: `packaging/homebrew/Formula/rewindagents.rb`,
`packaging/homebrew/README.md`.

What it does: a standard Python-virtualenv Homebrew formula
(`Language::Python::Virtualenv`, `virtualenv_install_with_resources`). It
fetches the `rewindagents` sdist directly from PyPI (pinned `url` + `sha256`),
depends on `python@3.12`, creates a dedicated venv under the Cellar's
`libexec`, pip-installs the sdist into it (no `resource` blocks needed — the
package has zero third-party Python dependencies), and links the resulting
`rewindagents` console script into `bin`. Its `test do` block runs
`rewindagents --help` and asserts the output contains the CLI's fixed
description string.

Current status: **not yet in a published tap.** There is no
`homebrew-rewindagents` GitHub repository. Today the formula can only be
installed locally, from a checkout of this repo:

```
brew install --build-from-source packaging/homebrew/Formula/rewindagents.rb
```

`brew tap Johnbjoseph-cybersec/rewindagents && brew install rewindagents`
will work once (and only once) that tap repository exists and carries this
formula — see `packaging/homebrew/README.md` for the exact layout it needs.

Validated: `ruby -c` (syntax) and `brew style` (lint), both passing — see
`forge-out/20261118-0140-rewind-big/installers-evidence.md` (0.0.9 pin),
`forge-out/20261118-0140-rewind-big/sprint2/hygiene-evidence.md` (1.0.0
re-pin), and `forge-out/20261118-0140-rewind-big/sprint2/hygiene-evidence.r1.md`
(round 2: `validate.py`'s CLI argument handling fixed; the `1.0.0` pin and
its sha256 were re-verified independently again, unchanged) for the exact
commands and output. A full `brew install --build-from-source` run (which
would download and build the sdist into a real Cellar prefix) has not been
exercised; the `sha256` was independently verified in every one of those
rounds by downloading the pinned sdist to a fresh scratch directory and
hashing it with `shasum -a 256`, separately from asking PyPI's own API for
the digest (same evidence files).

## npm

Files: `packaging/npm/package.json`, `packaging/npm/bin/rewindagents.js`.

What it does: `rewindagents.js` is a zero-dependency Node shim (no npm
`dependencies`, `engines.node >= 18`). On every invocation it:

1. Checks that `python3` is on `PATH` and reports Python 3.10 or newer
   (`python3 -c 'import sys; ...'`); if `python3` is missing or too old, it
   prints one clear line to stderr (no stack trace) and exits 2.
2. Creates a dedicated virtual environment at
   `$HOME/.rewindagents/npm/venv-<version>` the first time it runs for that
   pinned version.
3. `pip install`s that same pinned `rewindagents==<version>` into the venv,
   once — a second run detects the venv's own `rewindagents` script already
   exists and skips both the venv creation and the pip install.
4. Execs the venv's `rewindagents` console script with `process.argv` passed
   through unchanged, `stdio` inherited, and `process.exit` set to the
   child's real exit code — so the CLI's 0 (done) / 1 (partial or file issue)
   / 2 (cannot run / usage) contract survives the shim untouched.

Current status: **not yet published to the npm registry.** There is no
`rewindagents` package on npmjs.com under this name. Today it can only be
run from a checkout of this repo, e.g.:

```
node packaging/npm/bin/rewindagents.js --help
```

or linked locally with `npm link` from inside `packaging/npm/`.

Validated end-to-end against a fresh scratch `$HOME`, both at the `0.0.9` pin
and again after the `1.0.0` re-pin below:

- First run: creates the venv, really pip-installs the pinned
  `rewindagents==<version>` from PyPI into it, then execs it; `rewindagents
  --version` exits 0 and prints `rewindagents <version>` (confirmed against
  `pip show rewindagents` inside that venv, whose `Version:` line matches).
- Second run against the same `$HOME`: the venv's `rewindagents` script is
  reused, not reinstalled — the run completes in a fraction of the time of
  the first (0.88s → 0.11s at the `1.0.0` re-verification).
- `python3` missing from `PATH`, and `python3` present but below 3.10: both
  print one clear line to stderr and exit 2, no traceback.
- A bad subcommand (argparse usage error) exits 2; `--version` exits 0 —
  the exit-code contract passes through the shim unchanged.

Exact commands and output tails are in
`forge-out/20261118-0140-rewind-big/installers-evidence.md` (0.0.9 pin),
`forge-out/20261118-0140-rewind-big/sprint2/hygiene-evidence.md` (1.0.0
re-pin), and `forge-out/20261118-0140-rewind-big/sprint2/hygiene-evidence.r1.md`
(round 2 re-verification, run again against a fresh scratch `$HOME`).

## Version note

Both installers are pinned to **1.0.0**. `v1.0.0` is now tagged, pushed, and
the version PyPI's own API (`https://pypi.org/pypi/rewindagents/json`,
`info.version`) reports as current; the sdist `url` and `sha256` in
`packaging/homebrew/Formula/rewindagents.rb` were re-pinned to that release's
own sdist and independently re-verified by downloading it and hashing it
(see the sprint2 evidence file above) — they no longer carry a
`RELEASE-TODO` comment, since that bump has now happened. `packaging/npm/package.json`'s `version` field is `1.1.0`; the npm shim's venv path and
`pip install` target (`PACKAGE_SPEC` in `packaging/npm/bin/rewindagents.js`) derive from that one field.

Status on 2026-11-18:
- Homebrew: published as the tap `Johnbjoseph-cybersec/homebrew-rewindagents`
  (`brew install johnbjoseph-cybersec/rewindagents/rewindagents`). That repository's CI installs the formula
  from source and runs `brew test` on `macos-latest` and `ubuntu-latest`; both passed and printed
  `rewindagents 1.1.0`.
- npm: published as `rewindagents` 1.1.1 (`npx rewindagents`). Checked from an empty home and npm cache:
  `npx --yes rewindagents --version` printed `rewindagents 1.1.1`.

## What neither channel does

Neither installer adds a second place that knows how to invoke Python, parse
the CLI's output, or interpret its exit codes. Both channels end by executing
the one real `rewindagents` entry point that PyPI already ships; the
Homebrew formula does it via a `bin` symlink into a venv it manages, the npm
shim does it via `spawn` + `stdio: 'inherit'` + exit-code passthrough. If the
CLI's behavior ever changes, nothing in `packaging/` needs to change to
match it, except the pinned version/hash themselves.
