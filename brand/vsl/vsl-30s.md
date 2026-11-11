# vsl-30s: The agent deleted the tests. Step back to twelve.

Aspect 16:9. 8 beats, 29 s of 30 s allowed, 66 spoken words. Rendered from beats.json by build.py; edit beats.json, not this file.

`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. Every command and every output line on screen is one the README or the recorded demo session (brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.

| # | Time | Voice | On screen | Visual |
|---|---|---|---|---|
| b01 | 0-3 | Step thirteen. The agent deletes your tests. |    13  Bash          rm -rf tests  [3 checkpointed] | Frame one, no fade-in: Spool terminal panel on Leader, the replay row in Commit Mono in Rewind. Above it the step ruler, thirteen Rule ticks, the playhead in Record on the last. Cites: `   13  Bash          rm -rf tests  [3 checkpointed]` |
| b02 | 3-6 | Step fourteen. It overwrites the config. |    13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | The second row types in; both rows are the one Rewind pair. A fourteenth tick appears and the Record playhead moves onto it. Cites: `   14  Write         app/config.py  [1 checkpointed]` |
| b03 | 6-10.5 | rewindagent replay lists every step. Twelve was the last good one. | rewindagent replay<br>   12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | The command types in Leader at the Playhead prompt and the list prints. On the second sentence row twelve takes the Rewind, rows thirteen and fourteen go back to Leader, and the Record playhead steps back to tick twelve. Cites: `one line per step: number, tool, file or command`, `   12  Read          tests/test_server.py` |
| b04 | 10.5-13 | So rewind to twelve. | rewindagent rewind 12 | Prompt back in Playhead, the command types in Leader in Commit Mono. The ruler holds, playhead on twelve. Cites: `files back to how they were right after step 12` |
| b05 | 13-16.5 | Four files back. The tests, and the config. | session demo: rewind to step 12 of 14 (did change 4 files)<br>  restore  tests/test_config.py<br>  restore  tests/test_server.py<br>  restore  tests/test_timeout.py<br>  restore  app/config.py | The report prints; the four restore lines are the Rewind lines, the header in Leader. Cites: `session demo: rewind to step 12 of 14 (did change 4 files)`, `  restore  tests/test_config.py`, `  restore  tests/test_server.py`, `  restore  tests/test_timeout.py`, `  restore  app/config.py` |
| b06 | 16.5-19.5 | And the rewind itself can be undone. | A rewind is undoable. | The last report line, the undo command, takes the Rewind; a fifteenth tick draws itself on the ruler in Rule. Caption under the panel in Hanken Grotesk, Reel on Leader. Cites: `  this rewind is step 15; undo it with: rewindagent rewind 14 --session demo`, `A rewind is undoable.` |
| b07 | 19.5-24.5 | Install it from the repository, then run rewindagent install in your project. | {repo_url}<br>not on PyPI yet<br>rewindagent install | Leader page, the repository placeholder in Commit Mono as the one Record line, the not-on-PyPI note under a Rule hairline in Tape. Then a small Spool panel with the install command in Leader. Cites: `From the repository`, `Not on PyPI yet.`, `adds the hook to .claude/settings.json in this project` |
| b08 | 24.5-29 | Your editor has had undo for decades. Now your agent does. | rewindagent<br>Ctrl+Z for AI coding agents: record, replay, rewind.<br>{site_url}<br>made by John B Joseph | End card on Reel: wordmark in Bricolage Grotesque 800, Leader, the mark with its Rewind playhead one tick behind the last; promise in Hanken Grotesk, Playhead; address in Commit Mono, Leader; a Rule hairline; the credit line in Playhead. Cites: `Ctrl+Z for AI coding agents: record, replay and rewind.` |

## Narration only

Step thirteen. The agent deletes your tests.

Step fourteen. It overwrites the config.

rewindagent replay lists every step. Twelve was the last good one.

So rewind to twelve.

Four files back. The tests, and the config.

And the rewind itself can be undone.

Install it from the repository, then run rewindagent install in your project.

Your editor has had undo for decades. Now your agent does.

made by John B Joseph
