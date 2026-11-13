# UX audit of the rewindagents site, pass 2 (2026-11-13)

Reader: a developer who uses Claude Code, Codex or Cursor, arrives from a GitHub link or a post, and gives the
page 30 seconds. Job: understand it, believe it, copy the install line.

State audited: commit 5321b0d (the first designer's alignment pass), rendered with headless Chrome at 1440, 834
and 390 (`ux-review/before/*` is the state before 5321b0d, `ux-review/after/*` is 5321b0d). Identity rule: the
paper-white page, black terminals, the ruler motif and one red accent stay (John rejected abcadd0).

## What 5321b0d already fixed (kept, not redone)

- One gutter (`--gap: 48px`) for every two-column grid, so hero, session, ledger, command rows and plans share
  their column edges.
- Wrapped terminal rows hang under their own column (`hang()`), and a `--flag value` pair never splits.
- `# or for every project` sits above the command it describes, not under it.
- The install section became command rows (text left, panel right) like the commands section.
- Pricing cards use subgrid, so both lists and both buttons start on one line.
- Tablet "How it works" became one row per step; docs step numbers moved into the gutter.

## What it did not fix: ranked findings

Impact: H = costs the 30-second reader the install or the belief, M = costs clarity or polish visibly, L = detail.

| # | Impact | Where (screenshot) | Element | Why it costs the reader | Fix |
|---|---|---|---|---|---|
| F1 | H | after/index-1440-hero.png, after/index-390-hero.png | hero | The install command is not on the first screen at any width. At 1440 it starts at y about 2,560; at 390 about 3,900, after the whole session. Bun and Warp put it in the hero (BENCHMARK.md). | Put the README's install line and the hook line in the hero as a terminal block, under the buttons on a phone, beside the facts on desktop. |
| F2 | H | every command panel | `pre.term` cmd rows | No way to copy a command in one action. A drag-select picks up the `$` and wrapped indents. A JavaScript copy button would break the tested promise "no scripts" (`tests/test_site.py` allows only the JSON-LD script; the footer says so too). | Scriptless: each command's text is `user-select: all`, so one click selects exactly the command (never the `$`), then Cmd/Ctrl+C. A one-line hint says so beside the hero install block. A true copy-to-clipboard button is deferred to John: it needs a script and a change to the tested promise. |
| F3 | H | after/index-1440-hero.png | hero terminal | The panel shows `replay` then `rewind`, but nothing marks which steps were the wreck, so the story (13 and 14 broke it, rewind 12 undid them) needs the clip section to be read first. | Panel head carries the ruler motif as a 14-tick timeline with the playhead on step 12 and 13 to 14 after it in grey; the two wreck rows in the replay tail are struck through (an annotation, labelled as one in the caption; the text is the CLI's own). |
| F4 | H | whole page | missing section | "A test replays the session" is said once in small print. The page makes eight checkable claims (tamper detection, refusal to rewind a tampered log, undo of a rewind, a real `sed` and `rm` put back, the hook always exits 0, branch leaves HEAD alone) and links none of them to evidence. For a tool with no users yet, the tests are the proof. | New section "Tested": each claim, the test file and the test function that checks it, linked to the file on GitHub, plus the README's test command. `build.py` fails if a named test does not exist, so the list cannot rot. |
| F5 | H | og:image | `<meta property="og:image">` | The share image is the 1280x640 GitHub social preview (2:1). LinkedIn, Slack and X crop to 1.91:1, so the edges are cut, and it is the first impression for most visitors. | A 1200x630 card rendered from the site's own CSS and the real rewind output; first `og:image`, with width, height and alt, plus `twitter:image`. The 1280x640 tag stays second (the site test pins it). |
| F6 | M | after/index-1440-hero.png | hero panel last row | `this rewind is step 15; undo it with: rewindagents rewind 14 --session demo` wraps and leaves `demo` alone on a line at 1440. | Hero and session panels at 12px with 18px side padding: the 77-character row fits the 597px column. |
| F7 | M | after/index-1440.png, install row | install panel | The single most important command, `pipx install git+https://github.com/Johnbjoseph-cybersec/rewindagents`, wraps after `cybersec/` at 1440. | Command-row panels at 12.5px: 72 characters fit the 7/12 column. |
| F8 | M | after/index-1440-hero.png | hero, between caption and facts | 5321b0d pinned the facts to the bottom of the panel column (`margin-top: auto`), which leaves a 110px hole under the caption at 1440. | The hero becomes two rows on one grid: promise and panel, then facts and install. No hole, and the install block lands above the fold. |
| F9 | M | after/index-1440-hero.png | hero lede | 70 words in six lines before the buttons; the reader has to finish a paragraph to reach any action. | Three sentences, about 40 words. Nothing removed from the page: branch and the limits link stay. |
| F10 | M | after/index-390.png (session panel) | replay table rows on a phone | 5321b0d capped the hanging indent at 6ch on phones, so `[1 checkpointed]` breaks into `[1` and `checkpointed]` back at the left edge, ten times in one panel. | Drop the cap: wrapped table rows continue under their own column (20ch leaves 25 characters, enough for every continuation in the session). |
| F11 | M | hero CTA | buttons | "Install" scrolls to a section, which the hero now shows. The two buttons should be the two next steps. | Primary "Read the docs", secondary "Source on GitHub". "Install" stays in the nav. |
| F12 | L | section labels | `ruler(n=7)` | With a new section the 7-tick label ruler would run out. | Label ruler gets one tick per section (8). |
| F13 | L | after/index-1440.png, clip | `demo.gif` | The GIF's first frame is an empty prompt, so with motion paused (screenshots, some readers) the clip is a black box. | Deferred: the GIF is built by `brand/demo/build.py`, outside this pass's scope (brand/site and ux-review only). Recommend a first frame that already shows the replay. |
| F14 | L | 390 nav | `.nav` | Five links wrap to a second row under the logo; fine, but it costs 44px of the first screen. | Deferred: changing the nav is structure. |
