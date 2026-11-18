# Live verification: what "live" means here, and the honest-status rules

rewindagents supports seven coding-agent CLIs (`rewindagents.agents.AGENTS`: claude, codex, cursor, gemini,
copilot, droid, qwen). Before this harness existed, six of those seven were tested only against *documented*
hook payloads -- fixtures built from each vendor's own docs (`tests/test_agents.py`), never from a real
process the agent itself started. Only Claude Code's hook had run inside a real session.

`harness/live/run.py` changes that one agent at a time, by actually running the agent CLI -- not by asserting
that it would probably work. The per-agent results live in `harness/live/evidence/*.json`; the table below is a
copy of them, and every live-status sentence in README.md, `src/rewindagents/agents.py` and the site follows
those files: `tests/live_evidence.py` loads them, and `tests/test_agents.py`, `tests/test_agents_more.py` and
`tests/test_site.py` fail if a page calls a `VERIFIED_LIVE` agent not yet live, or calls any other agent live.
(`brand/launch/` and `brand/vsl/` are dated launch drafts and a recorded video; their status lines stay as they
were written.)

## Results: the run of 2026-11-18

| Agent | CLI version (`--version`) | Status | Log records | Notes |
|---|---|---|---|---|
| Claude Code | 2.1.294 (Claude Code) | `VERIFIED_LIVE` | 2 | |
| Codex | codex-cli 0.170.0 | `VERIFIED_LIVE` | 2 | |
| Cursor | 2026.11.17-f532c45 | `VERIFIED_LIVE` | 3 | |
| Gemini CLI | 0.68.0 | `VERIFIED_LIVE` | 4 | |
| Copilot CLI | GitHub Copilot CLI 1.0.114 | `VERIFIED_LIVE` | 2 | |
| Droid | 1.14.0 | `RAN_NO_LOG` | 0 | signed in, no model plan or API key: the agent made no tool call |
| Qwen Code | 0.28.0 | `RAN_NO_LOG` | 0 | signed in, no model plan or API key: the agent made no tool call |

`VERIFIED_LIVE` means: the agent made a real tool call in a scratch project, the hook wrote a pre and a post
record to that project's log, and `rewindagents rewind 0 --dry-run` printed a restore plan. For every agent the
real home-directory config was byte-identical before and after (`real_config_check.unchanged: true`).
`RAN_NO_LOG` is not a hook failure that was observed; it is the absence of a test: with no tool call there was
nothing for the hook to see. Droid and Qwen Code stay "tested with the documented payloads, not yet in a live
session" until a run with a model plan or API key produces their evidence
(`PYTHONPATH=src .venv/bin/python harness/live/run.py --agent droid --agent qwen`).

The Claude Code plugin (`plugin/`) has its own record, `harness/live/evidence/claude-plugin.json`, from a
`claude -p --plugin-dir plugin` session the same day; it is not one of the seven hook keys and
`validate.py` does not check it.

### The headless command per agent, and why each flag is there

Exactly as `harness/live/run.py`'s `HEADLESS` table builds them (`PROMPT` is the one-file prompt):

| Agent | Command | Why |
|---|---|---|
| Claude Code | `claude -p PROMPT --permission-mode bypassPermissions --setting-sources project --output-format json` | `-p` prints and exits; `bypassPermissions` skips the approval prompt for the write; `--setting-sources project` loads only the scratch project's `.claude/settings.json`, never the user's own settings; `--output-format json` keeps the printed result machine-readable. (The rewind check takes its session id from the recorded log, for every agent.) |
| Codex | `codex exec --trust --dangerously-bypass-hook-trust --skip-git-repo-check -s workspace-write PROMPT` | `exec` is the headless form. Codex loads a project's `.codex/` config, hooks included, only in a trusted project (`--trust`), and runs a project hook only after it has been reviewed once (`/hooks`), which a fresh scratch project has never had, so this one invocation bypasses the review. The scratch project is not a git repository (`--skip-git-repo-check`). `--full-auto` is gone in 0.170.0; `-s workspace-write` lets the write through. The harness also closes stdin: without a terminal, `codex exec` otherwise waits for more input until the timeout. |
| Cursor | `cursor-agent -p PROMPT --force` | `-p` prints and exits; `--force` skips the confirmation a file write would otherwise ask for. |
| Gemini CLI | `env GEMINI_CLI_TRUST_WORKSPACE=true gemini -p PROMPT --yolo` | `-p` prints and exits; `--yolo` accepts every tool call. A headless run refuses an untrusted folder, and `--skip-trust` runs without loading the project's `.gemini/settings.json`, so the hook never fires; the environment variable trusts the scratch folder, the same thing a user does once in the interactive trust prompt. |
| Copilot CLI | `copilot -p PROMPT --allow-all-tools --trust-folder` | `-p` prints and exits; `--allow-all-tools` removes the approval per tool. Without `--trust-folder` an untrusted project's `.github/hooks/` are not loaded and nothing is recorded. |
| Droid | `droid exec PROMPT --auto medium` | `exec` is the headless form; `--auto medium` lets file edits through without an approval. |
| Qwen Code | `qwen -p PROMPT --yolo` | Qwen Code forked Gemini CLI and keeps its flags. |

What this means for a user: Gemini CLI and Copilot CLI run a project's hooks only in a folder you have
trusted, and Codex runs a project hook only after you review it once (`/hooks`) and loads project config only
in a trusted project. The README says the same.

### The timeout: 300 seconds

Each agent invocation runs under a hard 300-second timeout (`HARD_TIMEOUT` in `run.py`; it was 120). On
2026-11-18 a Gemini CLI run that went on to pass met API 503 responses, and the CLI's own retry backoff pushed
it past 120 seconds; a timeout that kills a run which would have passed reports `FAILED` for a reason that has
nothing to do with the hook. 300 seconds leaves room for that and still bounds a CLI that hangs.

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
   hard 300-second timeout (see "The timeout" above). A prompt that writes exactly one small file is enough to exercise the whole
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
- **Keeping real payloads as fixtures.** The live runs prove the hooks fire and checkpoint; the payloads
  those sessions sent are not yet saved as test fixtures beside the documented ones. That, and the Droid and
  Qwen Code runs, are on the README's Roadmap.
