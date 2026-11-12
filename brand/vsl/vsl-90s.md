# vsl-90s: Your agent deleted the tests. Here is how you get them back.

Aspect 16:9. 21 cards, 90 s of 90 s allowed, 167 words on the cards. No voice: the cards carry the words, over the music bed. Rendered from beats.json by build.py; edit beats.json, not this file.

`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. Every command and every output line on screen is one the README or the recorded demo session (brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.

| # | Time | Card | Proof on screen | Motion |
|---|---|---|---|---|
| b01 | 0-3.3 | Your agent just ran **fourteen steps**. |  | Frame one on Leader paper: the line builds word by word out of a mask, big, in Bricolage Grotesque; the step ruler at the top draws fourteen ticks left to right, the Record playhead riding the newest tick. Cites: `brand/demo/manifest.json: fourteen replay rows` |
| b02 | 3.3-7.7 | Then it **deleted your tests** and overwrote your config. |    12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | Same scene, the camera still pushing in: the headline swaps (old line masks up and out, the new one rises in). A Spool panel under it: row twelve in Leader, then rows thirteen and fourteen type in and take the Rewind. Cites: `   13  Bash          rm -rf tests  [3 checkpointed]`, `   14  Write         app/config.py  [1 checkpointed]` |
| b03 | 7.7-10.8 | Can you get them **back**? | git status --short<br> M README.md<br> M app/config.py<br> M app/server.py<br> D tests/test_config.py<br> D tests/test_server.py | Rewind wipe: the playhead sweeps right to left across the frame and the old scene slides back under it. git status prints; the two deleted test paths are struck through in Rewind, one after the other. Cites: ` D tests/test_config.py`, ` D tests/test_server.py` |
| b04 | 10.8-14.9 | Three parts: **the problem**, how it works, the fix. | the problem<br>how it works<br>the fix | A roadmap: three ticks on a short rule, each label rising in under its tick as the line names it; the problem in Record, the parts still to come in Tape. |
| b05 | 14.9-19.9 | Why can't git help? The third test was **never committed**. |     6  Write         tests/test_timeout.py  [1 checkpointed]<br>untracked: git has no copy of it | Rewind wipe. The ruler's playhead scrubs back from fourteen to six and two Rule brackets close round tick six. The step six row (the agent wrote tests/test_timeout.py) prints in Rewind; a never committed tag in Tape under it. Cites: `    6  Write         tests/test_timeout.py  [1 checkpointed]`, `tracked and untracked files, but not git-ignored ones` |
| b06 | 19.9-24.6 | Claude Code's docs: shell-only changes **aren't tracked**. | "A file that only Bash commands changed isn't tracked ..."<br>Claude Code docs, checkpointing | Rewind wipe to a quote card: the sentence from Claude Code's checkpointing page in Commit Mono builds in, isn't tracked underlined in Record; the source in Tape. Cites: `A file that only Bash commands changed isn't tracked and stays as it is.` |
| b07 | 24.6-28.9 | So what would help? Think of a **flight recorder**. |  | Rewind wipe to a type card: the question, then the analogy, centred on paper, flight recorder in Record. |
| b08 | 28.9-33.1 | It keeps every move, so you can **replay** it. | flight recorder   every move, kept | The analogy map draws: a hairline grid of two columns; flight recorder on the left, every move, kept on the right. |
| b09 | 33.1-36.6 | So how does rewindagents **record your agent**? | flight recorder   every move, kept<br>the agent's log   every tool call, kept | Same map, held: the second row lands under the first, aligned column for column, the agent's log in Record. Cites: `Every tool call goes into a tamper-evident, hash-chained log` |
| b10 | 36.6-40.8 | Every tool call goes into one **hash-chained log**. | .rewindagents/log.jsonl<br>each record holds the SHA-256 of the one before | Rewind wipe. Seven record cards in Spool draw in left to right, each joined to the one before by a hairline that draws as the card lands (the chain); the log path and the SHA-256 rule under them. Cites: `tamper-evident, hash-chained log`, `Each record holds the SHA-256 of the record before it` |
| b11 | 40.8-45.2 | Before each edit or shell command, files are **saved**. |    13  Bash          rm -rf tests  [3 checkpointed]<br>saved before, scanned after | Rewind wipe. Two Rule brackets close round tick thirteen on the ruler; the step thirteen row in a Spool panel; on the beat only its three checkpointed mark turns Rewind; the note saved before, scanned after in Tape. Cites: `the current bytes of the target file are copied`, `project's files before the command, scans again after it`, `   13  Bash          rm -rf tests  [3 checkpointed]` |
| b12 | 45.2-51 | So **which step** would you rewind to? | rewindagents replay<br>   10  Edit          README.md  [1 checkpointed]<br>   11  Bash          git status --short<br>   12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | Rewind wipe. rewindagents replay types; the last five rows print in Leader with nothing highlighted, the ruler full at fourteen. The frame holds: no answer shows before the next card. Cites: `one line per step: number, tool, file or command` |
| b13 | 51-54.2 | **Twelve,** because thirteen is the delete. |    10  Edit          README.md  [1 checkpointed]<br>   11  Bash          git status --short<br>   12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | Same panel: row twelve takes the Rewind and the ruler's playhead scrubs back two ticks to twelve. Cites: `   12  Read          tests/test_server.py` |
| b14 | 54.2-58.5 | One command, and **four files** come back. | rewindagents rewind 12<br>session demo: rewind to step 12 of 14 (did change 4 files)<br>  restore  tests/test_config.py<br>  restore  tests/test_server.py<br>  restore  tests/test_timeout.py<br>  restore  app/config.py | Rewind wipe (the rewind itself). rewindagents rewind 12 types; the report prints with the four paths struck through, then the strikes pull back right to left one by one and the paths turn Rewind: the deleted files restoring in reverse. Cites: `files back to how they were right after step 12`, `session demo: rewind to step 12 of 14 (did change 4 files)`, `  restore  tests/test_config.py`, `  restore  tests/test_server.py`, `  restore  tests/test_timeout.py`, `  restore  app/config.py` |
| b15 | 58.5-63 | Even the rewind can be **undone**. | rewindagents rewind 12<br>session demo: rewind to step 12 of 14 (did change 4 files)<br>  restore  tests/test_config.py<br>  restore  tests/test_server.py<br>  restore  tests/test_timeout.py<br>  restore  app/config.py<br>  this rewind is step 15; undo it with: rewindagents rewind 14 --session demo | Same panel: the restore lines settle to Leader, the undo line prints in Rewind and a fifteenth tick grows on the ruler. Cites: `  this rewind is step 15; undo it with: rewindagents rewind 14 --session demo`, `A rewind is undoable.` |
| b16 | 63-66.8 | The analogy breaks: recorders **can't undo** a crash. | flight recorder   every move, kept<br>the agent's log   every tool call, kept<br>flight recorder   can't undo the crash | Rewind wipe back to the analogy map: the two rows return in Tape and a third row draws under them, flight recorder, can't undo the crash. |
| b17 | 66.8-69.8 | This one puts your **files back**. | flight recorder   every move, kept<br>the agent's log   every tool call, kept<br>flight recorder   can't undo the crash<br>the agent's log   rewind 12: files back | Same map: the fourth row, the agent's log, rewind 12: files back, lands in Record; the one row that has no flight-recorder twin. Cites: `files back to how they were right after step 12` |
| b18 | 69.8-74 | Preview with diff. Take back **one file** with --only. | rewindagents diff 12<br>+++ b/tests/test_config.py<br>rewindagents rewind 12 --only src/db.py | Rewind wipe. Two commands from the README, each typing into its own Spool chip as its sentence lands. Cites: `what taking it back to step 12 would change`, ``rewind N --only PATH` puts back only those files`, `+++ b/tests/test_config.py: printed by `rewindagents diff 12` on the demo session (brand/demo/scenario.py, tests/test_vsl_render.py)` |
| b19 | 74-79.2 | You can now see **every step** and the change it made. | rewindagents ui<br>the timeline runs on 127.0.0.1 only | Match cut: the ruler's playhead drops into the real rewindagents ui timeline (screenshot of the demo session), the camera pushes in on the rewound steps; the command in a small Spool chip, the 127.0.0.1 note in Tape. Cites: `opens the timeline in your browser`, `It listens on 127.0.0.1 only` |
| b20 | 79.2-84.2 | Apache-2.0. Standard library only. **Not on PyPI yet.** | rewindagents init<br>Claude Code: has run in real sessions<br>Six other agents: tested, not yet in a live session<br>{repo_url} | Rewind wipe. The three short sentences build one a line; under them four ruled rows rise in: rewindagents init in a small Spool chip, Claude Code's status, the other six agents' status (tested, not yet in a live session), then the repository address in Tape. One red thing on the card: the headline's 'Not on PyPI yet.' (The old 'Up next' bridge card is folded in here: review-textcut.json fix 6.) Cites: `Apache-2.0`, `No dependencies beyond the standard library`, `Not on PyPI yet.`, `From the repository`, `looks for the agents it supports (Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, Droid, Qwen Code)`, `The Claude Code hook has run in real sessions`, `tested with the documented payloads, not yet in a live session of any of them` |
| b21 | 84.2-90 | Your editor has had undo for decades. **Now your agent does.** | rewindagents<br>Ctrl+Z for AI coding agents: record, replay, rewind.<br>{site_url}<br>made by John B Joseph | The last rewind wipe turns the paper to Reel: the line builds at the top in Leader, then the wordmark with its playhead in Rewind, the promise in Playhead, the address in Commit Mono and the credit line. Cites: `Ctrl+Z for AI coding agents: record, replay and rewind.` |

## Teaching script

The input of the explainer-teaching gate: `teach_lint.py brand/vsl/vsl-90s.md`. There is no voice; each NARRATOR: line is a card's on-screen text.

- New terms: rewind, hash-chained log

## HOOK
NARRATOR: Your agent just ran fourteen steps.
[OST: 12  Read          tests/test_server.py]
[OST: 13  Bash          rm -rf tests  [3 checkpointed]]
[OST: 14  Write         app/config.py  [1 checkpointed]]
NARRATOR: Then it deleted your tests and overwrote your config.
[OST: git status --short]
[OST: M README.md]
[OST: M app/config.py]
[OST: M app/server.py]
[OST: D tests/test_config.py]
[OST: D tests/test_server.py]
NARRATOR: Can you get them back?
[OST: the problem]
[OST: how it works]
[OST: the fix]
NARRATOR: Three parts: the problem, how it works, the fix.

## WHY IT MATTERS
[OST: 6  Write         tests/test_timeout.py  [1 checkpointed]]
[OST: untracked: git has no copy of it]
NARRATOR: Why can't git help? The third test was never committed.
[OST: "A file that only Bash commands changed isn't tracked ..."]
[OST: Claude Code docs, checkpointing]
NARRATOR: Claude Code's docs: shell-only changes aren't tracked.

## ANALOGY
NARRATOR: So what would help? Think of a flight recorder.
[OST: flight recorder   every move, kept]
NARRATOR: It keeps every move, so you can replay it.

## CONCEPT
[OST: flight recorder   every move, kept]
[OST: the agent's log   every tool call, kept]
NARRATOR: So how does rewindagents record your agent?
[OST: .rewindagents/log.jsonl]
[OST: each record holds the SHA-256 of the one before]
NARRATOR: Every tool call goes into one hash-chained log.
[OST: 13  Bash          rm -rf tests  [3 checkpointed]]
[OST: saved before, scanned after]
NARRATOR: Before each edit or shell command, files are saved.

## WORKED EXAMPLE
[OST: rewindagents replay]
[OST: 10  Edit          README.md  [1 checkpointed]]
[OST: 11  Bash          git status --short]
[OST: 12  Read          tests/test_server.py]
[OST: 13  Bash          rm -rf tests  [3 checkpointed]]
[OST: 14  Write         app/config.py  [1 checkpointed]]
NARRATOR: So which step would you rewind to?
[PAUSE vsl-90s.b12]
- Line: So which step would you rewind to?
- Hold: 5.8 s
- Answer: Step twelve, the last step before the delete.

## REVEAL
[OST: 10  Edit          README.md  [1 checkpointed]]
[OST: 11  Bash          git status --short]
[OST: 12  Read          tests/test_server.py]
[OST: 13  Bash          rm -rf tests  [3 checkpointed]]
[OST: 14  Write         app/config.py  [1 checkpointed]]
NARRATOR: Twelve, because thirteen is the delete.
[OST: rewindagents rewind 12]
[OST: session demo: rewind to step 12 of 14 (did change 4 files)]
[OST: restore  tests/test_config.py]
[OST: restore  tests/test_server.py]
[OST: restore  tests/test_timeout.py]
[OST: restore  app/config.py]
NARRATOR: One command, and four files come back.
[OST: rewindagents rewind 12]
[OST: session demo: rewind to step 12 of 14 (did change 4 files)]
[OST: restore  tests/test_config.py]
[OST: restore  tests/test_server.py]
[OST: restore  tests/test_timeout.py]
[OST: restore  app/config.py]
[OST: this rewind is step 15; undo it with: rewindagents rewind 14 --session demo]
NARRATOR: Even the rewind can be undone.

## BREAK
[OST: flight recorder   every move, kept]
[OST: the agent's log   every tool call, kept]
[OST: flight recorder   can't undo the crash]
NARRATOR: The analogy breaks: recorders can't undo a crash.
[OST: flight recorder   every move, kept]
[OST: the agent's log   every tool call, kept]
[OST: flight recorder   can't undo the crash]
[OST: the agent's log   rewind 12: files back]
NARRATOR: This one puts your files back.

## RECAP
[OST: rewindagents diff 12]
[OST: +++ b/tests/test_config.py]
[OST: rewindagents rewind 12 --only src/db.py]
NARRATOR: Preview with diff. Take back one file with --only.
[OST: rewindagents ui]
[OST: the timeline runs on 127.0.0.1 only]
NARRATOR: You can now see every step and the change it made.

## BRIDGE
[OST: rewindagents init]
[OST: Claude Code: has run in real sessions]
[OST: Six other agents: tested, not yet in a live session]
[OST: {repo_url}]
NARRATOR: Apache-2.0. Standard library only. Not on PyPI yet.
[OST: rewindagents]
[OST: Ctrl+Z for AI coding agents: record, replay, rewind.]
[OST: {site_url}]
[OST: made by John B Joseph]
NARRATOR: Your editor has had undo for decades. Now your agent does.

## Cards only

Your agent just ran fourteen steps.

Then it deleted your tests and overwrote your config.

Can you get them back?

Three parts: the problem, how it works, the fix.

Why can't git help? The third test was never committed.

Claude Code's docs: shell-only changes aren't tracked.

So what would help? Think of a flight recorder.

It keeps every move, so you can replay it.

So how does rewindagents record your agent?

Every tool call goes into one hash-chained log.

Before each edit or shell command, files are saved.

So which step would you rewind to?

Twelve, because thirteen is the delete.

One command, and four files come back.

Even the rewind can be undone.

The analogy breaks: recorders can't undo a crash.

This one puts your files back.

Preview with diff. Take back one file with --only.

You can now see every step and the change it made.

Apache-2.0. Standard library only. Not on PyPI yet.

Your editor has had undo for decades. Now your agent does.

made by John B Joseph
