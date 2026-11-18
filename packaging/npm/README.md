# rewindagents

Undo for AI coding agents, including `rm -rf` and other shell commands. Record every tool call your agent makes,
see what changed, and take back one step, one file or a whole session.

```sh
npx rewindagents --version
npx rewindagents init        # add the hook for the coding agents installed here
npx rewindagents summary     # after a bad run: what the agent did
npx rewindagents rewind 12   # put the files back as they were after step 12
```

This npm package is a thin launcher: on first run it creates a private Python virtualenv under
`~/.rewindagents/npm/` and installs the matching `rewindagents` release from PyPI into it, then runs it. It needs
Python 3.10 or newer. Exit codes pass through unchanged. If you already use Python tools,
`pipx install rewindagents` installs the same CLI directly.

macOS and Linux. Local only: no account, no network after install. Apache-2.0.

Docs, source and the full README: https://github.com/Johnbjoseph-cybersec/rewindagents
