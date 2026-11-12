# vsl-90s: Step back to twelve: rewindagents on a real session

Aspect 16:9. 20 beats, 89.5 s of 90 s allowed, 213 spoken words. Rendered from beats.json by build.py; edit beats.json, not this file.

`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. Every command and every output line on screen is one the README or the recorded demo session (brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.

| # | Time | Voice | On screen | Visual |
|---|---|---|---|---|
| b01 | 0-3 | Step thirteen. The agent deletes your tests. |    13  Bash          rm -rf tests  [3 checkpointed] | Frame one, no fade-in: a Spool terminal panel on Leader, one replay row in Commit Mono, the row in Rewind. Above the panel the step ruler: thirteen Rule ticks on a hairline, the playhead in Record on the last one. Cites: `   13  Bash          rm -rf tests  [3 checkpointed]` |
| b02 | 3-6 | Step fourteen. It overwrites the config. |    13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | The second row types in under the first; both rows now one Rewind pair, the thing to look at. The ruler gains a fourteenth tick and the Record playhead moves onto it. Cites: `   14  Write         app/config.py  [1 checkpointed]` |
| b03 | 6-9.5 | Git status agrees. Two test files, gone. | git status --short<br> M README.md<br> M app/config.py<br> M app/server.py<br> D tests/test_config.py<br> D tests/test_server.py | Same Spool panel. The command types at the Playhead prompt in Leader, the five status lines print in Leader, then the two D lines turn Rewind. Cites: ` D tests/test_config.py`, ` D tests/test_server.py` |
| b04 | 9.5-14.5 | There were three. The third was never committed. Git can't return it. |     6  Write         tests/test_timeout.py  [1 checkpointed]<br>never committed | The step ruler slides back: the Record playhead travels from tick fourteen to tick six. In the Spool panel the row for step six appears in Rewind; under the panel, never committed in Hanken Grotesk, Tape on Leader. Cites: `    6  Write         tests/test_timeout.py  [1 checkpointed]`, `tracked and untracked files, but not git-ignored ones` |
| b05 | 14.5-17.5 | But rewindagents recorded all fourteen steps. | rewindagents replay<br>   10  Edit          README.md  [1 checkpointed]<br>   11  Bash          git status --short<br>   12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | The command types in Leader at the Playhead prompt, then the replay list prints one row per tick while the ruler fills to fourteen ticks in Rule; the panel settles on the last five rows. Rows thirteen and fourteen in Rewind, the rest in Leader. Cites: `one line per step: number, tool, file or command`, `   13  Bash          rm -rf tests  [3 checkpointed]`, `   14  Write         app/config.py  [1 checkpointed]` |
| b06 | 17.5-20.5 | Step twelve was the last good one. |    12  Read          tests/test_server.py | Rows thirteen and fourteen return to Leader; row twelve takes the Rewind. On the ruler the Record playhead steps back two ticks and sits on twelve, the two ticks after it in Rule grey. Cites: `   12  Read          tests/test_server.py` |
| b07 | 20.5-22.5 | So rewind to it. | rewindagents rewind 12 | The Playhead prompt comes back and the command types in Leader in Commit Mono. The ruler holds still, playhead on twelve. Cites: `files back to how they were right after step 12` |
| b08 | 22.5-26.5 | Four files back: all three tests and the config. | session demo: rewind to step 12 of 14 (did change 4 files)<br>  restore  tests/test_config.py<br>  restore  tests/test_server.py<br>  restore  tests/test_timeout.py<br>  restore  app/config.py | The report prints in the Spool panel. The four restore lines turn Rewind, one per spoken item, the header line stays Leader. Cites: `session demo: rewind to step 12 of 14 (did change 4 files)`, `  restore  tests/test_config.py`, `  restore  tests/test_server.py`, `  restore  tests/test_timeout.py`, `  restore  app/config.py` |
| b09 | 26.5-31 | And the rewind is step fifteen. You can undo the undo. |   this rewind is step 15; undo it with: rewindagents rewind 14 --session demo<br>A rewind is undoable. | The restore lines return to Leader and the last line of the report, the one that gives the undo command, takes the Rewind. On the ruler a fifteenth tick draws itself after fourteen in Rule. The caption sits under the panel in Hanken Grotesk, Reel on Leader. Cites: `  this rewind is step 15; undo it with: rewindagents rewind 14 --session demo`, `A rewind is undoable.` |
| b10 | 31-35 | The first twelve steps stay. So does the new test. | git status --short<br> M README.md<br> M app/config.py<br> M app/server.py<br>?? tests/test_timeout.py | The status prints in Leader; the untracked line, the file git could not return, is the one Rewind line. On the ruler ticks one to twelve are solid Reel, the playhead in Record on twelve. Cites: ` M README.md`, ` M app/config.py`, ` M app/server.py`, `?? tests/test_timeout.py`, `the tests are back; the first 12 steps stay` |
| b11 | 35-41 | Every tool call goes into a hash-chained log. Edit one record and verify names it. | rewindagents verify<br>.rewindagents/log.jsonl<br>each record holds the SHA-256 of the one before | Cut to Leader. The step ruler fills the width, and each tick becomes a short line of JSONL in Commit Mono, Reel, joined to the next by a Rule hairline. One record in the middle shifts a character; its hairline breaks and that record alone is marked in Record. Then the verify command in a small Spool panel. Cites: `tamper-evident, hash-chained log`, `Each record holds the SHA-256 of the record before it`, `makes `verify` fail and name the first bad record` |
| b12 | 41-45.5 | Before every edit, the hook copies the file as it is. | Write  Edit  MultiEdit  NotebookEdit<br>.rewindagents/objects/<sha256> | Leader ground. Four tool names in Commit Mono, Tape, on one row. Under one tick of the ruler a small file card in Spool drops a copy into a row labelled with the objects path; the copy is outlined in Record. Cites: `the current bytes of the target file are copied`, `to `.rewindagents/objects/<sha256>`` |
| b13 | 45.5-51.5 | Around every Bash command it saves first, scans after. So step thirteen kept three copies. |    13  Bash          rm -rf tests  [3 checkpointed]<br>saved before, scanned after | Two Rule brackets close around tick thirteen on the ruler, one before it, one after it, labelled in Hanken Grotesk, Tape. Below, the step thirteen row in a Spool panel, and only the three checkpointed mark in Rewind. Cites: `project's files before the command, scans again after it`, `   13  Bash          rm -rf tests  [3 checkpointed]` |
| b14 | 51.5-57 | rewindagents install adds the Claude Code hook. It has run in real sessions. | cd /path/to/your/project<br>rewindagents install<br>Claude Code: has run in real sessions | Spool panel on Leader, both commands type in Leader at the Playhead prompt. Beside the panel a status row in Hanken Grotesk, Reel, with one Record tick in front of it. Cites: `adds the hook to .claude/settings.json in this project`, `The Claude Code hook has run in real` |
| b15 | 57-65 | Codex and Cursor: built from the vendors' hook documentation, tested with the documented payloads. Not yet in a live session. | rewindagents install --agent codex<br>rewindagents install --agent cursor<br>built from the vendors' hook documentation<br>tested with the documented payloads<br>not yet in a live session | The same panel, two more install lines in Leader. Beside it the status rows continue in Reel, each set as spoken; the last row, not yet in a live session, is the one Record line, and its tick on the ruler is drawn open, an outline in Rule. Cites: `built from the vendors' hook documentation`, `documented payloads, not yet in a live session` |
| b16 | 65-71.5 | Files over twenty megabytes aren't copied. Over twenty thousand files, no scan, and rewind says so. | files over 20 MB: noted, not copied<br>over 20,000 files: not scanned, reported | Leader page headed limits in Bricolage Grotesque, Reel. Two rows in Commit Mono, Reel, each under a Rule hairline, the numbers tabular. The word reported is the one Record word. Cites: `Files over 20 MB are noted and not copied.`, `A project with more than 20,000 files is not scanned; the call is still recorded and `rewind` reports it.` |
| b17 | 71.5-76 | Export it as one HTML page. Find it later with sessions. | rewindagents export<br>.rewindagents/replay-<session>.html<br>rewindagents sessions | Spool panel: the export command and the path it writes in Leader. A plain page in Leader slides in beside it, the step ruler across its top, one step row with its diff in Commit Mono. Then the sessions command, its line marked latest in Rewind. Cites: `writes .rewindagents/replay-<session>.html`, `One HTML file with the whole session`, `every session in the log` |
| b18 | 76-81 | Apache-2.0, standard library only. Not on PyPI yet: install from the repository. | Apache-2.0<br>Python 3.10 or newer, standard library only<br>not on PyPI yet<br>{repo_url} | Leader page, four rows in Commit Mono, Reel, separated by Rule hairlines, left aligned. The repository placeholder row is the one Record line. Cites: `Apache-2.0`, `Python 3.10 or newer`, `no dependencies beyond the Python standard library`, `Not on PyPI yet.`, `From the repository` |
| b19 | 81-85 | A paid Cloud tier is planned. Not built, not priced. | Cloud tier: planned<br>planned: cloud sync, shareable replay links<br>not built, not priced | Leader page with a small planned label outlined in Record beside the heading. The items in Tape on ruled rows, their ticks drawn open in Rule because nothing here is built. Cites: `A paid Cloud tier (cloud sync, shareable replay links, long retention, session search): planned, not built`, `not priced` |
| b20 | 85-89.5 | Your editor has had undo for decades. Now your agent does. | rewindagents<br>Ctrl+Z for AI coding agents: record, replay, rewind.<br>{site_url}<br>made by John B Joseph | End card on Reel, like the end of a tape: the wordmark in Bricolage Grotesque 800, Leader, with the mark beside it, the playhead in Rewind one tick behind the last. The promise in Hanken Grotesk, Playhead; the address in Commit Mono, Leader; a Rule hairline; the credit line in Playhead. Cites: `Ctrl+Z for AI coding agents: record, replay and rewind.` |

## Narration only

Step thirteen. The agent deletes your tests.

Step fourteen. It overwrites the config.

Git status agrees. Two test files, gone.

There were three. The third was never committed. Git can't return it.

But rewindagents recorded all fourteen steps.

Step twelve was the last good one.

So rewind to it.

Four files back: all three tests and the config.

And the rewind is step fifteen. You can undo the undo.

The first twelve steps stay. So does the new test.

Every tool call goes into a hash-chained log. Edit one record and verify names it.

Before every edit, the hook copies the file as it is.

Around every Bash command it saves first, scans after. So step thirteen kept three copies.

rewindagents install adds the Claude Code hook. It has run in real sessions.

Codex and Cursor: built from the vendors' hook documentation, tested with the documented payloads. Not yet in a live session.

Files over twenty megabytes aren't copied. Over twenty thousand files, no scan, and rewind says so.

Export it as one HTML page. Find it later with sessions.

Apache-2.0, standard library only. Not on PyPI yet: install from the repository.

A paid Cloud tier is planned. Not built, not priced.

Your editor has had undo for decades. Now your agent does.

made by John B Joseph
