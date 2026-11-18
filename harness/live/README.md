# harness/live/ -- live agent verification

Runs each of rewindagents' seven supported coding-agent CLIs (claude, codex, cursor, gemini, copilot, droid,
qwen -- the keys of `rewindagents.agents.AGENTS`) against a real, disposable scratch project, and writes one
honest evidence JSON per agent under `harness/live/evidence/`. See `docs/live-verification.md` for the method
and the rules behind each status; this file is the how-to-run.

## Run it

From the repo root, with the repo's own virtualenv and `PYTHONPATH=src` (no extra install, standard library
only):

```
PYTHONPATH=src .venv/bin/python harness/live/run.py --all
PYTHONPATH=src .venv/bin/python harness/live/run.py --agent claude --agent codex   # a subset
PYTHONPATH=src .venv/bin/python harness/live/validate.py                          # schema-check the evidence
.venv/bin/python harness/live/test_run.py -v                                      # this harness's own tests
```

`run.py` prints one block per agent (status, notes if any, the evidence file path) and exits 1 only if an
agent's check itself failed outright (a timeout or an unexpected error) -- `NOT_INSTALLED` and
`INSTALL_BLOCKED` are expected, reportable outcomes on a machine that does not have every agent CLI, and do
not make `run.py` exit non-zero. `validate.py` exits 1 if any evidence file is missing, malformed, or
internally inconsistent (for example `VERIFIED_LIVE` claimed with zero log records).

`validate.py` also accepts explicit paths, which is what lets a shell-expanded
`validate.py harness/live/evidence/*.json` (or any other file, including one that does not exist) actually
check those files instead of silently falling back to the hardcoded list above:

```
.venv/bin/python harness/live/validate.py harness/live/evidence/*.json   # check exactly these files
.venv/bin/python harness/live/validate.py /path/to/some/copy.json        # check one arbitrary file
```

Each path's expected agent key is its filename stem (`claude.json` -> `claude`), the same rule the
hardcoded default list uses.

## What it does, per agent

1. Detects the CLI binary on PATH, using the exact candidate names `rewindagents init` itself looks for
   (`rewindagents.init.BINARIES`), and records its `--version` line.
2. Absent -> writes `NOT_INSTALLED` evidence and stops there. This harness never installs an agent CLI.
3. Present -> makes a fresh scratch project in a new temp directory (`tempfile.mkdtemp`, outside the repo) and
   runs the real `rewindagents install --agent <a> --settings <scratch>/<that agent's project config path>` --
   project-scoped only. It never points at, and never writes, a real agent config file under the home
   directory. The real config's sha256 is read before and after the whole check and compared; a mismatch is
   printed to stderr as a safety violation (it has never happened in a run of this harness) *and* recorded in
   the evidence file itself as `real_config_check: {"path": ..., "unchanged": bool}`, so the safety check's
   result is part of the durable artifact, not only a conditional line of console output.
4. Drives the agent non-interactively with one tiny file-writing prompt, cwd set to the scratch project,
   under a hard 120-second timeout, using that agent's own documented headless ("print and exit") form. The
   agent process is started as the leader of its own process group (`run._run_isolated`); if it times out,
   the harness kills the *whole* group (`os.killpg(SIGKILL)`), not just that one process, so a CLI that
   forked a background worker of its own does not leave that worker running as an orphan after the harness
   has moved on. `test_run.py` has the regression test (a fake binary that backgrounds a long sleep).
5. Reads the scratch project's `.rewindagents/log.jsonl` and checks it holds at least one "pre" record and one
   "post" record, then runs `rewindagents rewind 0 --dry-run` in the scratch project to exercise (without
   changing anything -- it is a dry run) a checkpoint-restore plan.
6. Writes `harness/live/evidence/<agent>.json`. `VERIFIED_LIVE` is used only when this run itself produced
   `log_records > 0` and all three `asserted` flags true.

## On this machine

Only `claude` is on PATH here. The other six come out `NOT_INSTALLED`, which is the correct, honest result --
not a weaker check pretending otherwise. If one of those CLIs is later installed, re-running the harness
drives it for real and reports exactly what it observed (`VERIFIED_LIVE`, `RAN_NO_LOG`, `INSTALL_BLOCKED` or
`FAILED`), never an assumed result.

## Scratch projects

Each check creates its own temp directory and leaves it on disk afterwards (its path is in the evidence file,
for anyone who wants to inspect the recorded log by hand); nothing under it is part of this repo. The system
temp directory cleans these up over time on its own; `harness/.gitignore` also excludes any scratch directory
a future run or a manual debug session might create under `harness/` itself.
