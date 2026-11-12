# vsl-30s: The agent deleted the tests. Step back to twelve.

Aspect 16:9. 7 cards, 27.4 s of 30 s allowed, 51 words on the cards. No voice: the cards carry the words, over the music bed. Rendered from beats.json by build.py; edit beats.json, not this file.

`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. Every command and every output line on screen is one the README or the recorded demo session (brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.

| # | Time | Card | Proof on screen | Motion |
|---|---|---|---|---|
| b01 | 0-3.3 | Your agent just ran **fourteen steps**. |  | Frame one on Leader paper: the line builds word by word out of a mask, big, in Bricolage Grotesque; the step ruler at the top draws fourteen ticks left to right, the Record playhead riding the newest tick. Cites: `brand/demo/manifest.json: fourteen replay rows` |
| b02 | 3.3-7.7 | Then it **deleted your tests** and overwrote your config. |    12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | Same scene, the camera still pushing in: the headline swaps (old line masks up and out, the new one rises in). A Spool panel under it: row twelve in Leader, then rows thirteen and fourteen type in and take the Rewind. Cites: `   13  Bash          rm -rf tests  [3 checkpointed]`, `   14  Write         app/config.py  [1 checkpointed]` |
| b03 | 7.7-10.8 | Can you get them **back**? | git status --short<br> M README.md<br> M app/config.py<br> M app/server.py<br> D tests/test_config.py<br> D tests/test_server.py | Rewind wipe: the playhead sweeps right to left across the frame and the old scene slides back under it. git status prints; the two deleted test paths are struck through in Rewind, one after the other. Cites: ` D tests/test_config.py`, ` D tests/test_server.py` |
| b04 | 10.8-14.9 | So **which step** would you rewind to? | rewindagents replay<br>   10  Edit          README.md  [1 checkpointed]<br>   11  Bash          git status --short<br>   12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | Rewind wipe. rewindagents replay types; the last five rows print in Leader with nothing highlighted, the ruler full at fourteen. The frame holds: no answer shows before the next card. Cites: `one line per step: number, tool, file or command` |
| b05 | 14.9-18.1 | **Twelve,** because thirteen is the delete. |    10  Edit          README.md  [1 checkpointed]<br>   11  Bash          git status --short<br>   12  Read          tests/test_server.py<br>   13  Bash          rm -rf tests  [3 checkpointed]<br>   14  Write         app/config.py  [1 checkpointed] | Same panel: row twelve takes the Rewind and the ruler's playhead scrubs back two ticks to twelve. Cites: `   12  Read          tests/test_server.py` |
| b06 | 18.1-22.4 | One command, and **four files** come back. | rewindagents rewind 12<br>session demo: rewind to step 12 of 14 (did change 4 files)<br>  restore  tests/test_config.py<br>  restore  tests/test_server.py<br>  restore  tests/test_timeout.py<br>  restore  app/config.py | Rewind wipe (the rewind itself). rewindagents rewind 12 types; the report prints with the four paths struck through, then the strikes pull back right to left one by one and the paths turn Rewind: the deleted files restoring in reverse. Cites: `files back to how they were right after step 12`, `session demo: rewind to step 12 of 14 (did change 4 files)`, `  restore  tests/test_config.py`, `  restore  tests/test_server.py`, `  restore  tests/test_timeout.py`, `  restore  app/config.py` |
| b07 | 22.4-27.4 | Your editor has had undo for decades. **Now your agent does.** | rewindagents<br>Ctrl+Z for AI coding agents: record, replay, rewind.<br>{site_url}<br>made by John B Joseph | The last rewind wipe turns the paper to Reel: the line builds at the top in Leader, then the wordmark with its playhead in Rewind, the promise in Playhead, the address in Commit Mono and the credit line. Cites: `Ctrl+Z for AI coding agents: record, replay and rewind.` |

## Cards only

Your agent just ran fourteen steps.

Then it deleted your tests and overwrote your config.

Can you get them back?

So which step would you rewind to?

Twelve, because thirteen is the delete.

One command, and four files come back.

Your editor has had undo for decades. Now your agent does.

made by John B Joseph
