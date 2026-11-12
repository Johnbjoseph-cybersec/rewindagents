# vsl-15s-vertical: Step back to twelve

Aspect 9:16. 5 beats, 13.5 s of 15 s allowed, 31 spoken words. Rendered from beats.json by build.py; edit beats.json, not this file.

`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. Every command and every output line on screen is one the README or the recorded demo session (brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.

| # | Time | Voice | On screen | Visual |
|---|---|---|---|---|
| b01 | 0-2.5 | Your agent just deleted the tests. |  D tests/test_config.py<br> D tests/test_server.py | Frame one: a tall Spool panel fills the middle of a Leader frame, the two lines large in Commit Mono in Rewind. Above it a short step ruler, fourteen Rule ticks, the playhead in Record on the last. Cites: ` D tests/test_config.py`, ` D tests/test_server.py` |
| b02 | 2.5-4.5 | And overwrote the config. |  M app/config.py | The two lines return to Leader; the new line below them is the Rewind line, set as large. Cites: ` M app/config.py`, `   14  Write         app/config.py  [1 checkpointed]` |
| b03 | 4.5-6.5 | Rewind to step twelve. | rewindagents rewind 12 | The panel clears to the Playhead prompt; the command types in Leader. On the ruler the Record playhead steps back two ticks. Cites: `files back to how they were right after step 12` |
| b04 | 6.5-10 | Four files back, as they were after step twelve. |   restore  tests/test_config.py<br>  restore  tests/test_server.py<br>  restore  tests/test_timeout.py<br>  restore  app/config.py | The four restore lines print large in Commit Mono, all four in Rewind as one group, readable at phone size. Cites: `session demo: rewind to step 12 of 14 (did change 4 files)`, `  restore  tests/test_config.py`, `  restore  tests/test_server.py`, `  restore  tests/test_timeout.py`, `  restore  app/config.py` |
| b05 | 10-13.5 | Your editor has undo. Now your agent does. | rewindagents<br>Ctrl+Z for AI coding agents: record, replay, rewind.<br>{site_url}<br>made by John B Joseph | Vertical end card on Reel: wordmark in Bricolage Grotesque 800, Leader, stacked over the promise in Hanken Grotesk, Playhead, wrapped to two lines; the address in Commit Mono, Leader; a Rule hairline; the credit in Playhead. The mark's playhead in Rewind. Cites: `Ctrl+Z for AI coding agents: record, replay and rewind.` |

## Narration only

Your agent just deleted the tests.

And overwrote the config.

Rewind to step twelve.

Four files back, as they were after step twelve.

Your editor has undo. Now your agent does.

made by John B Joseph
