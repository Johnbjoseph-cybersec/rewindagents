# Changing course: from undo button to proving ground

Status: a proposal to John with a working prototype on branch `worktree-agent-a9dac934443c1e3b9`. Nothing here
is on `main`, published or announced. Web sources were read on 2026-11-13; quotes are the few lines needed.

## 1. Where the product stands (from `FIRST_RUN.md`)

In a fresh venv, every subcommand did what the README says: the hook recorded two sessions and a `sed -i`,
`rewind` and `branch` put files back and could be undone, `export`/`bundle`/`import`/`gc` worked, errors named
the next step. The friction was all past the undo: nothing answered "which step wrote this line", "what did
the agent contribute to this commit", or "would another attempt have done better from here". rewindagents
holds the most precise record on the machine of how each file reached its bytes, and only uses it to go back.

Undo on its own is a feature, not a category, and the agent vendors now ship it themselves (Claude Code's
`/rewind` and checkpointing; Entire's CLI rewinds checkpoints, below). The question is what this record becomes
when it is the base other work stands on.

## 2. How the category-makers moved

**Linux: a primitive that everyone could build on, and nobody had to ask permission to.** Torvalds announced
it on comp.os.minix on 25 August 1991 as "just a hobby, won't be big and professional like gnu"
([ZDNet, Linux at 30](https://www.zdnet.com.au/article/linus-torvalds-on-linuxs-30th-birthday/);
[Wired, 2009](https://wirednews.pages.dev/2009/08/0825-torvalds-starts-linux)). His first licence barred
commercial use; moving to the GNU GPL in 1992 (sources differ on the month:
[Stackscale](https://stackscale.com/blog/linux), [History of Linux](https://cavac.at/cavacopedia/History_of_Linux))
is what let distributions and companies build on it and give back. The lesson for us: be the neutral layer
under many vendors, with the format and the code open, so the ecosystem grows on top rather than around.

**GitHub: the place where the work lives and is shared.** Launched in 2008 on top of git, an open primitive it
did not own, with forks and pull requests as the social unit of work
([noze.it on GitHub's founding](https://www.noze.it/en/insights/github-founding/);
[Wikipedia](https://www.wikipedia.org/wiki/GitHub)). Microsoft agreed to buy it for $7.5 billion in June 2018
(same sources). The lesson: the fork-and-compare loop (fork, change, open a pull request, review the
difference) became the unit everybody organised around. GitHub did not invent git; it made git's branches
into something people could see, compare and discuss.

**GitLab: buyer-based open core.** The handbook rule is that "the likely buyer determines which tier", with
most functionality free and paid tiers aimed at managers, directors and executives
([GitLab handbook, tiering](https://handbook.gitlab.com/handbook/product/tiering-guidance-for-features/);
[pricing model](https://handbook.gitlab.com/handbook/company/pricing)). The lesson: what an individual
developer needs stays open; what a lead or an org buys (aggregation, policy, history across people) is paid.

**Sentry: open code, paid convenience.** A 71-line Django plugin in 2008 under BSD; BSL in 2019; the
Functional Source License in 2023, which turns into Apache/MIT after two years and blocks a competing hosted
Sentry ([Sentry blog](https://blog.sentry.io/introducing-the-functional-source-license-freedom-without-free-riding);
[TechCrunch](https://techcrunch.com/2023/11/20/with-functional-source-license-sentry-wants-to-grant-developers-freedom-without-harmful-free-riding/amp)).
Sentry says it does not monetize self-hosted Sentry. The lesson: the hosted service is the business; the
licence only has to stop someone else selling the same hosted service.

**Supabase: an open alternative to a closed incumbent, hosted as the default.** "The open-source Firebase
alternative", Apache 2.0, self-hostable with Docker; the hosted plans carry the paid features (SSO, compliance
reports) ([OpenTechHub](https://www.opentechhub.io/supabase/); [UI Bakery](https://uibakery.io/blog/supabase-alternatives)).

**PostHog: MIT core, `ee/` directory, cloud recommended.** The repo is MIT except `ee/`, which needs a licence
([github.com/posthog/posthog](https://github.com/posthog/posthog)); its FAQ calls self-hosting "not
recommended" and Cloud "the recommended option for all teams" ([posthog.com/faq](https://posthog.com/faq)).

**The pattern.** Each one (a) gave developers a primitive that works alone, offline, for free; (b) made the
primitive's output a shared object (a kernel tree, a repository, a pull request, an event stream); (c)
charged for the place many people's shared objects meet, at the level of the buyer who is not the individual
user. None of them won by adding features to a tool that already existed.

## 3. The field in November 2026

| Who | What it does | What it does not |
|---|---|---|
| Claude Code | Checkpoints and `/rewind`; its docs say a file only Bash changed "isn't tracked" ([checkpointing](https://code.claude.com/docs/en/checkpointing)). Parallel sessions in git worktrees (`claude --worktree`), branching from the default branch or `HEAD` ([worktrees](https://code.claude.com/docs/en/worktrees)). | A worktree starts from a commit, not from step 12 of a session with its uncommitted state; nothing compares what two worktrees did. |
| Cursor 2.0 | Up to eight agents on one prompt, each in a worktree or remote machine, and you pick ([changelog](https://cursor.com/en-US/changelog/2-0)). | Cursor models in Cursor only; starts from the prompt, not from a recorded step; comparing is by eye. Staff on the forum call best-of-N's use case narrow ([forum](https://forum.cursor.com/t/what-s-the-point-of-multiple-agents/141805)). |
| Entire (Dohmke, ex-GitHub CEO) | $60M seed, February 2026; open-source CLI that records agent sessions and links them to commits, with rewind, resume and `entire blame` ([launch post](https://entire.io/blog/hello-entire-world); [Open Source For You](https://opensourceforu.com/2026/02/ai-code-transparency-platform-entire-unveiled-by-ex-github-ceo-with-60m-seed)). Its docs list Claude Code, Codex, Cursor, Copilot CLI, Gemini CLI, OpenCode, Pi ([docs](https://docs.entire.com/cli/checkpoints.md)). | Its checkpoints page has nothing for comparing two runs or agents (read 2026-11-13). |
| git-ai | Line-level AI attribution in git notes, `git ai blame`; its site now says "Git AI is now part of OpenAI" ([usegitai.com](https://usegitai.com/docs/how-git-ai-works)). | Notes say files created via Bash may be missed when the agent is not at the repository root. |
| Agent Trace (Cursor) | Open spec, 0.1.0 RFC, January 2026: which line ranges came from which conversation and contributor type ([agent-trace.dev](https://agent-trace.dev/); [InfoQ](https://www.infoq.com/news/2026/02/agent-trace-cursor)); supported by Cognition, Cloudflare, Vercel, git-ai, Jules, Amp, OpenCode per coverage. | "This spec intentionally does not define how traces are stored"; no tamper evidence; tool calls are not recorded. |

Practitioner writing converges on one more thing: public benchmarks shortlist, and teams decide on tasks
drawn from their own history ([developertoolkit.ai](https://developertoolkit.ai/en/ecosystem/models/benchmarks/);
[Kunal Ganglani](https://www.kunalganglani.com/blog/benchmark-ai-coding-tools-repo)). These are blog posts,
not studies, and I take them as a signal of the question people ask, not as measured demand.

## 4. The candidate courses

Scored High / Medium / Low with the reason; no numbers that were not measured.

| | User pull | Defensibility | Revenue path | Stdlib-buildable now |
|---|---|---|---|---|
| **A. Open format for recording agent work ("agent black box")** | Low directly: developers adopt tools, tools adopt formats. | Low: the attribution format seat is taken by Agent Trace with seven named backers; a second spec splits a small field. Our edge (a hash-chained record of effects, incl. Bash) is a property, not a standard. | Indirect only. | Yes, entirely. |
| **B. Sessions as shareable, reviewable history linked to PRs** | High: AI-written PRs are hard to review, and the market says so. | Low for us: Entire ($60M, GitHub's former CEO, same agents) and git-ai (now OpenAI) are on exactly this ground; we already ship the `attach` action and would be the fourth entrant. | Clear (hosted review), but against better-funded, better-placed rivals. | Yes for local parts; the hosted part is the product. |
| **C. Team/enterprise provenance and audit of agent changes** | Medium: a real buyer (security, compliance), slow cycles. | Medium: the tamper-evident chain is a real edge. | Strongest per seat. | Yes. But this product's own scope rule is "record and undo only; it never stands between the agent and its tools, and does no enforcement", and a sibling product already owns compliance evidence. It would collide on both. |
| **D. Forkable, comparable runs** | Medium and rising: vendors ship parallel attempts (Cursor's eight agents, Claude Code worktrees) because users ask "would another try be better"; teams want to choose agents and models on their own code. | High: a vendor will not credibly compare itself with its competitors, and nobody else starts a run from step N of a recorded session with its exact files (uncommitted, untracked, Bash-touched) and a verified origin. Most of the machinery (plan, rewind, branch, seven agents' hooks, verified log) exists here already. | Hosted: run forks in parallel sandboxes, keep a team's comparison history, re-run a team's recorded starting points when a model, prompt or `CLAUDE.md` changes. A buyer (the engineering lead who pays for agent seats and tokens) who is not the individual user, per GitLab's rule. | Yes: git worktrees, hashes, difflib, subprocess. |

## 5. The pick: D, forkable and comparable runs

**The course in one line: rewindagents becomes the neutral proving ground for coding agents, where any
recorded step is a starting point any agent can continue from, and the runs are compared on what they did,
not on what anyone claims.**

Why D and not B or A:

1. **It is where we are clearly better, not at parity.** On B we would be the fourth tool linking sessions to
   commits, behind a $60M company and an OpenAI-owned project, with no capability they lack. On D nobody
   offers the combination: a cross-vendor recorder (seven agents), exact reconstruction of any step's files
   including what only a shell command touched, and a verified link from every run back to its origin.
2. **Neutrality is the moat a vendor cannot copy.** Cursor's best-of-N compares Cursor's models in Cursor;
   Claude Code's worktrees run Claude. A team choosing between them needs a referee that belongs to neither.
   This is the Linux position: the layer under many vendors.
3. **It turns the archive into an asset.** Every recorded session becomes a reusable starting point: "step 0
   of last Tuesday's migration, plus the test we wrote after". That is the "tasks from your own history" the
   practitioner guides describe, made a byproduct of using the tool rather than a project.
4. **It contains A and B instead of competing with them.** The run log is the open record (A); a comparison
   is the natural thing to attach to a pull request (B): "we tried three agents from step 12, this is the one
   whose check passed, here is how the others differed". Agent Trace output can be emitted from the same log
   later; we interoperate with the standard rather than fight it.
5. **It fits the scope rule.** It never blocks, gates or governs anything: it copies files, records, runs the
   user's own check, and reports.

What would change my mind: if a vendor ships cross-agent comparison from a mid-session state, or if in the
first 30 days people try `fork` but never run `compare` (the proving-ground premise is wrong and B's review
use is the pull). `ROADMAP.md` names the measurements.

## 6. The foundation on this branch (working, tested)

- `rewindagents fork N --name X [--session S] [--dir D]` (`src/rewindagents/runs.py`): a git worktree on
  `rewindagents/run/X` (plain directory outside git) holding the files as `rewind N` would leave them; its own
  `.rewindagents/` starts with a `fork` record naming session, step, the source log's head hash and every
  starting file's SHA-256, with copies in the run's store. Refuses what it cannot rebuild exactly; a failure
  half-way removes the worktree, branch and directory.
- `rewindagents compare [RUN ...] [--check CMD] [--diff A B] [--json]`: per run, agents and their tool calls
  since the start, files changed/created/deleted, lines +/-; per file, which runs ended with identical bytes;
  the user's check command's exit code in each; a git-appliable diff between two runs.
- `tests/test_runs.py`: 19 tests, all through the real hook. Among them: the fork's files equal step N's
  (incl. an untracked file, and a file a Bash `rm` deleted later) while the project's files, `HEAD` and index
  are unchanged; a project in a subdirectory of a repository becomes a plain directory; an agent in the run records into the run's log, not the project's, and `rewind` works there;
  an unscanned step, a tampered log, a bad name, a path inside the project, and a failure injected half-way
  each leave nothing behind; identical outcomes get the same letter; `--check` exit codes; `git apply` of
  `compare --diff proj b` makes the project's files equal run b's; `gc` in a run keeps the starting copies.
  All 19 fail on the previous commit (the module does not exist there).

### Try it in five minutes

With no agent (the script feeds the real hook the payloads Claude Code sends, then makes a second attempt by
hand in the fork):

```sh
python3 -m venv /tmp/ra && /tmp/ra/bin/pip install -q <this branch's checkout>
sh ux-review/try-runs.sh /tmp/ra/bin/rewindagents
```

It prints the recorded session, the fork, then (from a real run on 2026-11-13):

```
  run       agents         steps  files  lines                 check
  shop      claude             1      1  +1 -1                 FAIL (exit 1)
  clamp     -                  0      1  +1 -1                 pass

  file     shop         clamp
  cart.py  changed A    changed B
```

With a real agent, in a project where `rewindagents init` has added the hook and a session is recorded:

```sh
rewindagents replay                         # pick the step to start from, say 12
rewindagents fork 12 --name codex-try       # ../<project>-codex-try, a worktree with step 12's files
cd ../<project>-codex-try && codex          # or claude, cursor, gemini ... with the same prompt or another
cd - && rewindagents compare --check "npm test"
rewindagents compare --diff <project> codex-try
```
