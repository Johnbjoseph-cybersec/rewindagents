# Roadmap for the proving-ground course (proposal, 2026-11-13)

This follows `TRANSFORMATION.md` and needs John's yes before any of it reaches `main`. Every outcome is
something we can count from files, logs, git or the payment provider; the figures are targets, not results.
Nothing here has users yet, and none are claimed.

## The split: open core vs paid hosted

GitLab's rule: what the individual developer needs is free; what a lead or an organisation buys is paid.

| Open core (Apache-2.0, local, stdlib, no network, no account, never blocks a tool call) | Paid hosted (opt-in upload; the local tool never needs it) |
|---|---|
| record, replay, diff, rewind, branch, export, bundle/import, gc, ui | |
| `fork N` and `compare` (built), `--check`, `--diff`, `--json` | a shared page per comparison, linkable from a PR or a chat |
| saved starting points ("tasks": a step plus its check) and `rerun` across agents, run on your machine | the same tasks run in parallel cloud sandboxes, so ten attempts do not occupy a laptop |
| the `attach` action putting a comparison table on a pull request | a team's comparison history across repos and people: which agent, model or prompt wins on which kind of task |
| the run format, documented, with conformance tests | scheduled re-runs of a team's tasks when a model, prompt or `CLAUDE.md` changes, with a report of what got worse |
| | retention, SSO, seats: the things an org buys |

The licence stays Apache-2.0 for everything installable. A hosted server, if its code is ever published,
can follow Sentry's FSL route so that nobody resells the same hosted service; that decision is John's.

## 30 days (to 2026-12-13): prove the loop with real agents

Build:
1. After John's yes: merge `fork`/`compare` to `main`; a docs-page panel for them (brand/site/, reviewed the
   usual way, original look kept).
2. A live pair: the same prompt from the same recorded step, once in Claude Code and once in Codex (or
   Cursor), both through their real hooks, compared. Keep the payloads as fixtures; this also answers the
   README's open item that the Codex and Cursor hooks have not run live.
3. `compare` in the pull request: the `attach` action posts the comparison table when the bundle holds runs.
4. Fork from a bundle: `import` then `fork` in a clean clone, so a teammate can take over from step N.
5. `export --agent-trace`: Agent Trace records from the log, so we interoperate with the attribution
   standard instead of competing with it.

Measure (each is a file or a command anyone can re-run):
- Time from `pip install` to the first `compare` table on a clean machine, with a stopwatch, written in
  `ux-review/`: target under 5 minutes with an agent installed, under 1 minute with `try-runs.sh`.
- Real fork-to-compare cycles on real repositories (ours count, labelled as ours), kept as bundles: target 10.
- Of everyone who tries it (issues, waitlist replies), how many mention `compare` or forking against how many
  mention only undo. If people fork and never compare, the premise is wrong: stop and go back to the review
  use (candidate B) before building the hosted layer.

## 90 days (to 2027-02-11): your history becomes your test set

Build:
1. `rewindagents task save N --check CMD --name X`: a step plus the check that judges it, kept in the log
   (hash-chained like everything else).
2. `rewindagents rerun X --agents claude,codex`: fork the task once per agent, start each agent's own
   headless mode in its run (the agents' CLIs talk to their vendors; rewindagents itself still makes no network
   connection), wait, compare. Nothing new is invented for "run an agent": the vendors' documented
   non-interactive commands are called as the user would call them.
3. Hosted beta (paid, opt-in): `compare --json` uploaded by the user to a hosted page per comparison and a
   team history; sandboxes to run a `rerun` in parallel.

Measure:
- Saved tasks per project that uses it (from the logs of projects that send us their counts, opt-in only).
- Hosted beta: teams that pay. Target: the first paying team; the price is set with John before the beta.
- Kill criterion: if no team will pay for parallel sandboxes plus history after 20 conversations, keep the
  open core and do not build more hosted.

## 365 days (to 2027-11-13): the referee for coding agents

Build:
1. The run format v1 as a short spec in the repository with conformance tests other tools can run, so a
   run made by another recorder can be compared here. Linux's lesson: be the layer under many vendors.
2. Hosted: re-runs of each team's tasks on every model or agent release they opt into, with a report of what
   passed before and fails now; per-task-type views of which configuration wins for this team's code; seats,
   SSO, retention.
3. Every agent the hook supports today (seven) plus any new one with a documented command hook, recorded in a
   live session each.

Measure:
- Teams on the hosted plan and revenue from them, from the payment provider; targets set with John at the
  90-day review, from what the beta actually showed rather than guessed now.
- Tools other than ours that produce or read the run format (counted by their repositories, not by claims).
- The open core's promise, tested on every release: no network, no account, stdlib only, the hook never
  blocks (the existing hardening tests plus `tests/test_runs.py`).
