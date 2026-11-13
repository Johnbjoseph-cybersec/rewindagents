# semverlite: bump (planned)

`bump(version, part)` returns the next version string. `part` is one of:

- `"major"`: X+1.0.0
- `"minor"`: X.Y+1.0
- `"patch"`: X.Y.Z+1, except that a version with a pre-release bumps to its own release
  (`1.2.3-rc.1` -> `1.2.3`)
- `"prerelease"`: if the version has a pre-release whose LAST identifier is numeric, increment it
  (`1.2.3-rc.1` -> `1.2.3-rc.2`); if it has a pre-release whose last identifier is not numeric, append `.1`
  (`1.2.3-rc` -> `1.2.3-rc.1`); with no pre-release, bump the patch and add `-0` (`1.2.3` -> `1.2.4-0`)

Build metadata is always dropped. Any other `part` raises `ValueError`. The input must parse (else
`ValueError`).
