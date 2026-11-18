# Homebrew tap layout for rewindagents

This directory is the *contents* of a future tap repository. It is not a tap
by itself: Homebrew only recognizes a tap when it lives in a GitHub repo named
`homebrew-<tapname>` under a user or org account, and is added with `brew tap`.

No `homebrew-rewindagents` repository exists yet. This file documents the
layout that repository would use once one is created and published; it does
not create or push any external repo.

## Repository layout

A tap named `rewindagents` would be a separate GitHub repository:

```
Johnbjoseph-cybersec/homebrew-rewindagents/
  Formula/
    rewindagents.rb
  README.md
```

- The repository name must be `homebrew-rewindagents` (the `homebrew-` prefix
  is required; `brew tap user/rewindagents` resolves to
  `github.com/user/homebrew-rewindagents`).
- Formulae live under `Formula/<name>.rb`, one file per formula, lower-case
  filename matching the formula's Ruby class name translated to
  `CamelCase < Formula` (here: `rewindagents.rb` defines `class Rewindagents`).
- `packaging/homebrew/Formula/rewindagents.rb` in *this* repo is the source of
  truth for that file's contents; publishing the tap means copying (or
  mirroring via CI) this file into the tap repo's `Formula/` directory.

## Installing from the tap, once it exists

```
brew tap Johnbjoseph-cybersec/rewindagents
brew install rewindagents
```

`brew tap` clones `homebrew-rewindagents` under
`$(brew --repository)/Library/Taps/`; `brew install rewindagents` then
resolves the formula from `Formula/rewindagents.rb` in that clone, same as any
formula in `homebrew-core`.

## Formula contents

See `packaging/homebrew/Formula/rewindagents.rb` in this repo. Summary:

- Fetches the `rewindagents` sdist from PyPI (`url` + `sha256` pinned to a
  specific released version).
- `depends_on "python@3.12"`.
- Installs with `virtualenv_install_with_resources` (`Language::Python::Virtualenv`):
  a dedicated venv under `libexec`, this sdist pip-installed into it with no
  resource blocks (the package has zero third-party Python dependencies), and
  its `rewindagents` console script linked into `bin`.
- `test do` block runs `rewindagents --help` and asserts the output contains
  the CLI's fixed description string.

## Current status

- The formula in this repo (`packaging/homebrew/Formula/rewindagents.rb`) is
  validated with `ruby -c` and `brew style` (see
  `forge-out/20261118-0140-rewind-big/installers-evidence.md` for the 0.0.9
  pin and `forge-out/20261118-0140-rewind-big/sprint2/hygiene-evidence.md`
  for the 1.0.0 re-pin, each with the exact commands and output observed).
- It has **not** been installed end-to-end with `brew install
  --build-from-source` (no tap or bottle build has been run); only static
  syntax/style validation and a manual pip-into-venv reproduction of the
  same install steps were performed. Record any future `brew install`
  verification run in a new evidence file.
- There is no published `homebrew-rewindagents` tap repository. Until one
  exists, this formula cannot be installed with `brew tap` + `brew install`;
  it can only be installed locally with `brew install --build-from-source
  packaging/homebrew/Formula/rewindagents.rb` from a checkout of this repo.
- The pinned `url`/`sha256` target PyPI release `1.0.0`, which is now the
  version PyPI's own API reports as current and which is tagged and pushed
  (`v1.0.0`) in this repo (see `docs/install-channels.md`). The formula's
  `RELEASE-TODO` comment has been removed now that the bump it marked has
  happened.
