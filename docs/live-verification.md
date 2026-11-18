# Live verification: what "live" means here, and the honest-status rules

rewindagents supports seven coding-agent CLIs (`rewindagents.agents.AGENTS`: claude, codex, cursor, gemini,
copilot, droid, qwen). Before this harness existed, six of those seven were tested only against *documented*
hook payloads -- fixtures built from each vendor's own docs (`tests/test_agents.py`), never from a real
process the agent itself started. Only Claude Code's hook had run inside a real session. `agents.py` and the
README both say so plainly, and `tests/test_launch.py` pins that exact wording until it stops being true for
a given agent.

`harness/live/run.py` is the mechanism that can make that wording stop being true, one agent at a time, by
actually running the agent CLI -- not by asserting that it would probably work. This page is the method and
the ground rules; the per-agent *results* live in `harness/live/evidence/*.json`, not here, and this
campaign's wording rule means those results are not restated as prose claims anywhere else yet (see
`docs/CLAIMS_DELTA.md`, owned by the coordinating session, for how a verified result turns into updated
README/agents.py text later).

## The method

For one agent key:

1. **Detect the binary.** `shutil.which()` over the exact candidate names `rewindagents init` uses
   (`rewindagents.init.BINARIES[agent]` -- for example cursor's `("cursor-agent", "cursor")`, because its
   newer CLI name `agent` is too generic to mean Cursor). Absent -> `NOT_INSTALLED`, and nothing further runs
   for that agent. This harness never installs an agent CLI itself.
2. **Scratch project.** A fresh, empty temp directory outside the repo. Every later step runs with that
   directory as `cwd`.
3. **Project-scoped install only.** `rewindagents install --agent <a> --settings <scratch>/<project config
   path>`, where the project config path is the exact one `rewindagents.agents.config_path()` names for that
   agent (`.claude/settings.json`, `.codex/hooks.json`, and so on). The harness never writes to, and never
   points `install` at, the agent's real home-directory config. It reads that real file's sha256 before and
   after the whole check (never writes it) and treats any change as a hard safety failure, printed to
   stderr; it has never happened in a run of this harness. The comparison result is also written into the
   evidence file as `real_config_check: {"path": <the real config path>, "unchanged": <bool>}` -- additive to
   the schema literally enumerated in this campaign's contract, added because the stderr line alone left no
   durable, on-disk proof that the safety check ran and passed for a given evidence file; flagged here for
   the coordinating session the same way a new install channel or a newly-verified agent would be, since a
   schema change is exactly the kind of thing that should not land unilaterally. If an agent's own CLI turned
   out to only honor a global, user-level config -- true of none of the seven today, per `agents.py`'s own
   sourcing -- the right status would be `INSTALL_BLOCKED` with the reason, not a silent fallback to writing
   the real file.
4. **Drive it headlessly.** One tiny, single-purpose prompt ("create this one file with this one line of
   text"), through the agent's own documented non-interactive form (`claude -p ...`, and so on -- see
   `harness/live/run.py`'s `HEADLESS` table for the exact argv and the doc each one is read from), under a
   hard 120-second timeout. A prompt that writes exactly one small file is enough to exercise the whole
   pre-record / checkpoint / post-record path without needing the agent to do anything agent-specific. The
   agent process is launched as the leader of its own new process group and session (`run._run_isolated`,
   `start_new_session=True`); on timeout the harness kills that *whole group* (`os.killpg(..., SIGKILL)`)
   rather than only the one process `subprocess.run`'s own timeout handling would signal. Without this, a
   hung agent CLI that had forked a background worker of its own would leave that worker running -- under a
   bypassed-permission session, past the point the harness already wrote its evidence and moved to the next
   agent. `harness/live/test_run.py` has the regression test: a disposable fake binary forks a long-sleeping
   grandchild and records its pid, the harness's timeout fires, and the test asserts the grandchild is dead a
   few seconds later.
5. **Assert against the real log**, not against what the agent CLI printed. The scratch project's
   `.rewindagents/log.jsonl` must hold at least one record with `"event": "pre"` and at least one with
   `"event": "post"` for that run. Then `rewindagents rewind 0 --dry-run` is run in the scratch project (a
   dry run changes nothing) and must print a restore plan -- this is the harness's `checkpoint_restored`
   check: proof that the checkpoint the pre-record made is actually usable to put the file back, not just
   that a record with a hash in it exists.
6. **Write one evidence file.** Exactly one `harness/live/evidence/<agent>.json` per agent, matching the
   schema in the sprint's frozen contracts. `harness/live/validate.py` schema-checks all seven and fails the
   build if any is missing, malformed, or internally inconsistent.

### The scrub rule

An evidence file is committed to the repo and read by anyone who clones it; it must never embed the real
machine's username in an absolute path. The only three fields a real run ever puts an absolute filesystem
path into are `commands`, `scratch_dir`, and `real_config_check["path"]` (the additive field described
above). Right before `run.py` writes an evidence record to disk, it replaces this machine's home-directory
prefix (`os.path.expanduser('~')`) with the literal `~` inside exactly those three fields -- every other
field (`status`, `log_records`, `agent_version`, `asserted`, `notes`, `ran_at`, `agent`) is untouched.
`harness/live/validate.py` enforces the result: any evidence file whose `commands`, `scratch_dir`, or
`real_config_check.path` still contains a literal `/Users/` or `/home/` segment is a schema violation, the
same way a `VERIFIED_LIVE` claim with no commands is -- a leaked absolute home path is exactly the kind of
defect a human skimming a green `validate.py` run would not notice on their own.

## The honest-status rules

These are the only five statuses, and the only conditions under which each may be written:

- **`NOT_INSTALLED`** -- no candidate binary found on PATH. Expected and correct for every agent this machine
  does not have installed; it is not a weaker form of passing and it is not an error.
- **`INSTALL_BLOCKED`** -- the binary is present, but a project-scoped install could not be written (for
  example, `rewindagents install` itself refused because this Python is a disposable `uvx`/`pipx run`
  environment). The evidence's `notes` field carries the exact reason observed. Nothing further is attempted.
- **`RAN_NO_LOG`** -- the agent CLI ran to completion but the scratch project's log holds zero records: either
  its hook never fired, or the agent made no tool call for the given prompt. This is a real, reportable
  result, not a retry trigger.
- **`FAILED`** -- something in the harness's own run of the agent did not complete as expected: the hard
  timeout was hit, the process could not be started, or the log has some records but not enough to satisfy
  every assertion (missing a pre or post record, or the checkpoint-restore dry run did not produce a plan).
  `FAILED` is also what an unexpected exception anywhere in one agent's check turns into, so that one agent
  misbehaving never silently stops the other six from being checked.
- **`VERIFIED_LIVE`** -- and only this status means what it says: this run of the harness itself produced
  `log_records > 0` in the scratch project's log, and all three of `asserted.pre_event`, `asserted.post_event`
  and `asserted.checkpoint_restored` are `true`, from commands this harness actually executed and a log it
  actually read. `harness/live/validate.py` enforces this as a hard rule across every evidence file: a
  `VERIFIED_LIVE` status with `log_records == 0` or any `asserted` flag `false` is a schema violation, not a
  judgement call left to whoever reads the file. The three boolean flags are not enough on their own, though
  -- a hand-edited file can set them to `true` without the harness having run anything. So `validate.py` also
  requires, whenever `status == VERIFIED_LIVE`, that `commands` is non-empty, `scratch_dir` is not `null`,
  and at least one command string names the agent's own binary (`rewindagents.init.BINARIES[agent]`): a real
  run always produces all three, and a fabricated record that only sets the flags is caught by them.
  `harness/live/test_run.py` has the regression test, built from exactly this corruption: a copy of a real
  evidence file edited to claim `VERIFIED_LIVE` with `log_records=5` and every flag `true` but
  `commands=[]`, `scratch_dir=null`, `agent_version=null` -- `validate.py` rejects it.

No status is ever asserted from documentation, from a prior run's evidence file, or from "this should work
the same way claude did" reasoning -- each evidence file reflects only what its own run observed. Re-running
the harness after installing a previously-absent agent CLI is how that agent's status changes; editing an
evidence file by hand is not a legitimate way to change it.

## What this does not cover

- **Windows.** The harness runs the POSIX headless forms only; the per-agent Windows shell forms
  (`agents.py`'s `win_shell`/`win_command_key`) are a separate, already-known gap (the CI Windows job is
  failing today, independent of this harness) and are out of scope here.
- **Every tool an agent can call**, not just file writes. The one-line prompt exercises the write/checkpoint
  path (the one every agent integration most needs to get right); it does not exhaustively drive every tool
  name each vendor's docs list.
- **Turning a result into a claim.** A `VERIFIED_LIVE` evidence file is the fact; updating README.md,
  agents.py's own comments, or the pinned wording in `tests/test_launch.py` to say so is deliberately a
  separate step (`docs/CLAIMS_DELTA.md`), owned elsewhere, so that a provable claim and the sentence that
  states it never drift apart.
