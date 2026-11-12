# rewindagents: onboarding, three emails

For people who asked for help getting started (on a waitlist issue or by writing in) and gave an email address
for it. There is no mailing list and nothing sends these automatically: they go by hand from John's address, one
person at a time, the first when they ask, the second a few days later, the third about a week after that. Skip
any the person no longer needs. Fill the addresses with `python3 brand/launch/fill.py onboarding-3-emails.md`.

## Email 1

Subject: rewindagents in two commands

Hi,

Here is the shortest path to your first recorded session.

Install it from the repository (it is not on PyPI yet). It needs Python 3.10 or newer on macOS or Linux (it uses a Unix file lock), and nothing beyond the standard library:

```sh
pipx install git+{repo_url}
rewindagents --version
```

Then, in the project your agent works in:

```sh
cd /path/to/your/project
rewindagents install
```

That adds the hook to `.claude/settings.json` in that project and keeps everything already in the file. For Codex or Cursor:

```sh
rewindagents install --agent codex
rewindagents install --agent cursor
```

Those two are tested with the payloads in the vendors' documentation, not yet in a live session. If yours sends something different, `rewindagents replay --step 12` (with your step number) prints what was recorded, and an issue with it would help.

From the next call on (for Codex, once the project's .codex/ folder is trusted and you have trusted the new hook with /hooks inside Codex), every tool call goes into `.rewindagents/log.jsonl`, which keeps itself out of your commits.

John

## Email 2

Subject: when a session goes wrong

Hi,

The day an agent deletes or overwrites the wrong thing, this is the order that works. Run it from the project directory.

```sh
rewindagents replay
rewindagents replay --step 12
rewindagents rewind 12 --dry-run
rewindagents rewind 12
```

`replay` gives one line per step, so the bad steps are easy to find. `replay --step 12` shows one step in full. `--dry-run` lists what a rewind would change without touching anything. `rewind 12` puts back the files the later steps changed, the way they were right after step 12, and says which ones it could not.

A rewind saves the current files first and is recorded as a step, so it prints the command that undoes it. If you want to keep what the agent did as well: in a git repository, `rewindagents branch 12 --name try2` first commits the current tree to the branch rewindagents/try2, without moving your HEAD or index (outside git it keeps the current files in the log only).

Before it writes anything, a rewind checks the log's hash chain and every stored copy it will restore from. If a file could not be put back (one over 20 MB, or a stored copy that no longer matches), it names it and exits 1. If a step was never scanned (a command in a project of more than 20,000 files), it says how many such steps there were; their changes are not put back.

John

## Email 3

Subject: three more commands, and one question

Hi,

Three things that are easy to miss:

```sh
rewindagents export
rewindagents sessions --grep config.py
rewindagents verify
```

`export` writes the whole session as one HTML page, with a diff for each changed text file up to 256 KB (longer diffs are cut at 400 lines): no scripts and nothing fetched. Paths inside the project are shown relative to it, but read the commands and results before you share it, because a command that names the full project path keeps it. `sessions --grep` finds the sessions that touched a file or ran a command. `verify` checks the log's hash chain and names the first bad record if there is one.

And the question: what did you expect rewindagents to do that it did not? A sentence is plenty. Replies decide what gets built next.

Thanks for trying it.

John

Repository: {repo_url}
Docs: {site_url}

made by John B Joseph
