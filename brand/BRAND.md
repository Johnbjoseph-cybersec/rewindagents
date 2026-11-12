# rewindagent - brand identity

Status: identity (RB1, written by Iris Kapoor, Creative Studio), logo set (RB2, see "Logo" below), the
demo GIF (RB2b, see "Demo GIF") and the site (RB3, see "Site").
Not self-graded; independent reviewers score the identity in brand/review.json, the demo in
brand/demo/review.json and the site in brand/site/review.json.

## One-line promise

Ctrl+Z for AI coding agents: record, replay, rewind.

## Positioning

rewindagent is an open-source recorder for coding agents. It writes every tool call an agent makes
(Claude Code, Codex and Cursor) into a tamper-evident, hash-chained JSONL log and saves a
copy of each file before the agent changes it. You can replay a session step by step, rewind the working
tree to any step, or keep the current files as a branch and then rewind. It never blocks, judges or stops an
action: the agent works at full speed and every action stays undoable. It is a developer tool, not a security
product, and it should feel like one: a flight recorder and a tape deck, plain, exact and a little
mechanical, sitting quietly in the repo until you need it.

## Audience

Developers and engineering teams who use coding agents and want to be able to take a bad step back.
We write for the person at the terminal, not for a buyer.

A paid tier may come later (cloud sync, shareable replay links, long retention, session search). Nothing
in the identity depends on it, and nothing is sold before it exists.

## Voice

Plain, exact, a little dry. We say what exists and what does not.

1. **Exact.** We give the real behaviour and the real limit.
   Example: "Files a Bash command changes are saved too, except git-ignored files and files over 20 MB; rewind tells you which ones it could not put back."
2. **Honest about status.** Planned things are called planned.
   Example: "Not on PyPI yet. Install it from the repository with pip. The Codex and Cursor hooks are tested with the documented payloads, not yet in a live session."
3. **Calm.** Mistakes happen; we do not dramatise them.
   Example: "The agent deleted the wrong folder. Step back one."
4. **Dry.** One small joke at most, never at the reader's expense.
   Example: "Undo is a feature your editor has had for decades."
5. **Hands-on.** Commands and file paths over adjectives.
   Example: "Run rewindagent verify and it names the first bad record."

Credit line, used exactly in footers: made by John B Joseph

## Words we never use

Scope words: never use or imply blocking, policy, enforcement, probing, spend, compliance or governance,
nor any term in the launch gate's scope guard (the enterprise AI-security vocabulary in the FIRE-1
boundary section of FIRE's PROJECTS.md). That second list is deliberately not spelled out here:
the gate scans every file in this repo, this one included, and fails the launch on a match.
tests/test_brand.py runs the same pattern over brand/, so a slip fails the tests first.

Also never: revolutionary, seamless, unleash, AI-powered, game-changer. No emoji. No section symbol.
No invented users, testimonials, customer logos, numbers or benchmarks.
No "secure", "protect" or "defend" as a pitch: we make actions undoable, we do not stand guard.

## Palette

Light first, like a printed log; a dark variant for terminals. Warm-neutral green-grey paper and a
record-button red. No purple or violet anywhere, no neon on black, no gradient. The red is a signal for the
one thing that matters on a page, not a theme.

| Name | Hex | Role |
|---|---|---|
| Leader | #F2F4F1 | Ground on light pages. Pale green-grey, like film leader, not cream. |
| Reel | #121412 | Primary text on light; ground on dark. |
| Spool | #1C201D | Dark surface: terminal, code blocks, replay timeline. |
| Tape | #55605A | Secondary text on light. |
| Record | #B82A16 | Accent on light: links, the record mark, one highlight per view. |
| Rewind | #FF7A59 | Accent on dark: the playhead, current step, links in terminals. |
| Playhead | #B9C2BB | Secondary text on dark. |
| Rule | #838C86 | Hairlines, tick marks, step ruler. Graphics only, never body text. |

Room for siblings: red-on-paper belongs to rewindagent. The SOC 2 evidence CLI and the security eval suite
choose their own hues and type; they should not reuse Record, Rewind or the tape-ruler motif, and rewindagent
must not use shield, padlock or generic security blue or green.

### Contrast table

Pairs are defined in contrast_check.py and the table below is its output. Do not edit the numbers by hand;
rerun `python3 brand/contrast_check.py` and paste. Body text needs 4.5, large text 3.0.

```
text      on        fg      bg      ratio  need  result / use
Reel      Leader    #121412 #F2F4F1 16.73  4.5   PASS (body, body text on paper)
Tape      Leader    #55605A #F2F4F1 5.92   4.5   PASS (body, secondary text on paper)
Record    Leader    #B82A16 #F2F4F1 5.62   4.5   PASS (body, links and accent text on paper)
Leader    Record    #F2F4F1 #B82A16 5.62   4.5   PASS (body, label on accent button / tag)
Leader    Reel      #F2F4F1 #121412 16.73  4.5   PASS (body, body text on dark)
Playhead  Reel      #B9C2BB #121412 10.13  4.5   PASS (body, secondary text on dark)
Rewind    Reel      #FF7A59 #121412 7.21   4.5   PASS (body, accent text on dark)
Leader    Spool     #F2F4F1 #1C201D 14.91  4.5   PASS (body, terminal text on dark surface)
Playhead  Spool     #B9C2BB #1C201D 9.03   4.5   PASS (body, terminal comments on dark surface)
Rewind    Spool     #FF7A59 #1C201D 6.42   4.5   PASS (body, terminal accent on dark surface)
Reel      Rewind    #121412 #FF7A59 7.21   4.5   PASS (body, label on accent block, dark ground)
Record    Leader    #B82A16 #F2F4F1 5.62   3.0   PASS (large, display headline accent on paper)
Rewind    Reel      #FF7A59 #121412 7.21   3.0   PASS (large, display headline accent on dark)
Rule      Leader    #838C86 #F2F4F1 3.13   3.0   PASS (large, rules and tick marks (graphical, 3.0))
Rule      Reel      #838C86 #121412 5.34   3.0   PASS (large, rules and tick marks on dark (graphical, 3.0))
15 pairs, 0 failing
```

## Type pairing

All free, open-licensed, self-hostable.

| Role | Font | Licence |
|---|---|---|
| Display (headings, wordmark text) | Bricolage Grotesque, 700 to 800 | SIL Open Font License 1.1 |
| Body | Hanken Grotesk, 400 to 600 | SIL Open Font License 1.1 |
| Mono (commands, hashes, step counters, code) | Commit Mono, 400 and 700 | SIL Open Font License 1.1 |

Use: sentence case headings, left aligned, tight tracking on display only. Hashes and step numbers always in
mono, tabular. Not used: Poppins, Plus Jakarta Sans, Inter, Space Grotesk, any serif.

## Logo (RB2, round 4 = RB2c)

Built by brand/logo/build.py (geometry + text outlined from the OFL font files) and rendered by
brand/logo/render.mjs (resvg). Look at brand/logo/contact-sheet.png: every asset, the 16 px drawing and the
mark at true 16, 32 and 64 px, and brand/logo/in-use.png (browser tab, README header on a light and a dark
page, avatar in circle crops): the reviewer reads the mark where it will be seen, not alone.

- Mark: a timeline playhead on a step ruler, scrubbed back, on a 16-unit grid (half units allowed; sharp
  from 32 px). Seven short, equal ticks (1 unit wide, 2.5 above the rule) at a 2-unit pitch on a half-unit
  rule: x 1, 3, 5, 7 recorded in ink, then the playhead at x 9, then x 11, 13, 15 rewound in Rule grey, with
  the rule grey after the playhead too, like the unplayed end of a scrubber. The playhead is the only tall
  element: an editor's handle in Record (a flat-topped pentagon 4 wide, 2 flat and 1.5 taper) on a 1-unit
  line that ends flush with the rule bottom, no neck between head and line. Ticks overlap the rule so no
  seam renders where they meet. In the mono version the ruler and playhead alone carry the idea.
- Changes from the brief below: the small left-pointing flag was dropped (bar plus flag read as the digit 1)
  and the playhead is one tick behind the last recorded step rather than one tick before the end; three
  rewound ticks read as "scrubbed back" where one grey tick needed explaining.
- favicon.svg / favicon-32.png are a separate drawing on whole pixels so nothing is anti-aliased at 16 px:
  1 px ticks at a 2 px pitch (three each side) on a 1 px rule, a 2 px playhead line with a flat-topped
  stepped head (two rows of 6 px, one of 4 px), and the rewound rule and ticks in Tape. The same drawing,
  scaled by whole pixels, serves 64 px tiles and the 20 px avatar crop.
- Files: logo-mark.svg (light), logo-mark-reverse.svg (dark), logo-mark-mono.svg (currentColor),
  logo-wordmark.svg / -reverse / -mono (horizontal), favicon.svg + favicon-32.png, avatar-512.png,
  logo-light.png and logo-dark.png (1024, stacked: the mark 544 px over a 760 px name), social-preview-1280x640.png
  (name, tagline, one real command in an outlined block, the credit, the mark at 448 px on the right, centred
  on the headline-to-command block).
- Wordmark: Bricolage Grotesque 800, tracking -0.02 em, no kerning table applied. In the horizontal lockup
  one grid unit is the "d" ascender height over 8.5, so the playhead rises a little above the ascenders, and
  the text baseline is the bottom of the rule and of the playhead.
- Palette fidelity is measured, not eyeballed: build.py records sample points (pixel, expected palette name)
  for every PNG in brand/logo/manifest.json; `python3 brand/logo/pngsample.py` prints the sampled hex next to
  the BRAND.md hex, and tests/test_logo.py fails on any mismatch.

## Demo GIF (RB2b)

brand/demo.gif, 1200 x 675, under 20 seconds, looping. Built by brand/demo/build.py from brand/demo/scenario.py:
a small project in a temporary folder, fourteen agent steps through the real Claude Code hook (the last two
run `rm -rf tests` and overwrite app/config.py), then the four commands the clip shows: `rewindagent replay`,
`git status --short`, `rewindagent rewind 12`, `git status --short`. Every line on screen is what those
commands printed; tests/test_demo.py plays the session again and fails on any difference, and reads the
GIF's size, play time, delays and colour table from the file.

- Look: the Leader ground with a Spool terminal on it (light first, a dark variant for terminals). Terminal
  text in Leader, comments and the prompt in Playhead, the mark in the title bar in mono Leader. Rewind is
  used once per view, for the thing to look at: the two steps that wrecked the repo in the replay list, then
  the restored files in the rewind report; when the next block appears the earlier one returns to Leader.
- Type: Commit Mono 400 for the terminal, Bricolage Grotesque 800 for the name, Hanken Grotesk 400 for the
  tagline and the credit, all outlined from the OFL files.
- Pacing: a comment line, the command typed at 25 characters a second, a short beat, the output, then a hold
  of two to three seconds with the prompt back. Every duration is on ffmpeg's 40 ms grid.
- Look at brand/demo/keyframes/ (the opening prompt and the end of each beat, full size) and
  brand/demo/contact-sheet.png before judging it; the per-frame sources are rebuilt into brand/demo/frames/.

## Site (RB3)

brand/site/index.html (landing), pricing.html and docs/index.html, built by brand/site/build.py and served by
GitHub Pages from brand/site/. The address lives in brand/site/config.json only (site_url); a bought domain is a
one-line change there plus a redirect.

- Nothing on a page is typed from memory: every command block is an sh block of the README, every number is a
  constant of the package, the terminal in the hero quotes brand/demo/manifest.json (the session behind the clip,
  which tests/test_demo.py replays), and every planned item on the pricing page is a phrase of this document.
  tests/test_site.py rebuilds the pages and fails on any difference.
- Look: Leader paper, Reel ink, Spool terminal panels with Leader text, Playhead for prompts and comments, Rewind
  for the one block to look at in a panel, Record for links and for the playhead in the section rulers. The step
  ruler opens every section: ticks on a hairline, the playhead on the section's number, the ticks after it in
  Rule grey. Left aligned; hairlines do the structuring. The footer is Reel, like the end of a tape.
- Type: Bricolage Grotesque 800 for headings, Hanken Grotesk 400 and 600 for text, Commit Mono for every command,
  number and label. Self-hosted WOFF2 files in brand/site/fonts/ with their OFL licences beside them.
- No scripts, no cookies, no analytics, nothing fetched from outside the site. Static HTML.
- Look at it before judging it: `bash ~/team-agents/fire/bin/render_html.sh brand/site/index.html 1440 <height> out.png`
  renders a page at 1440 and, through an iframe, at 390.

## VSL scripts (RB4a)

brand/vsl/beats.json is the one source for the three launch videos (vsl-90s, vsl-30s, vsl-15s-vertical): per
beat the time, the narration, the lines on screen, the shot and what backs it. brand/vsl/build.py renders the
scripts (brand/vsl/<name>.md) and the captions (brand/vsl/<name>.srt) from it; edit the JSON, never the outputs.
The videos themselves (voice, music, motion) are not made yet; the renders are the next brand task, and they are
judged on full-resolution frames by an independent reviewer, never by the builder.

- Nothing on screen is typed from memory: every command is a line of an sh block of the README or one of the four
  commands of the recorded demo session, and every terminal line is one that session printed
  (brand/demo/manifest.json, replayed by tests/test_demo.py). Every number is a limit of the package or a number
  that session printed. tests/test_vsl.py checks each one.
- The address is `{site_url}` and `{repo_url}` in every script and caption, substituted from brand/site/config.json
  when the videos are rendered.
- Every video ends on the same end card: the name, the one-line promise, the address, the credit line.
- Narration at most 2.6 words a second per beat, beats between 1.5 and 9 seconds, captions in two lines of 42
  characters, built from the narration word for word.
- The claims are checked by claim-verifier, not by the writer or the builder, into brand/vsl/claims.json; the
  review carries the SHA-256 of the beats it read, and the tests fail if the beats change after it.

## Launch kit (RB5)

brand/launch/ holds the launch drafts: producthunt.md, show-hn.md, x-thread.md, reddit.md, linkedin-for-jj.md (JJ
decides and posts; FIRE never touches LinkedIn), waitlist-welcome.md and onboarding-3-emails.md (sent by hand, one
person at a time; there is no mailing list). None is posted while the launch is on hold.

- The address is `{site_url}`, `{repo_url}` or `{waitlist_url}` in every file; `python3 brand/launch/fill.py <file>`
  prints the file filled from brand/site/config.json, ready to paste.
- Every command is a README command or one of the demo session's, every number is a limit of the package, a number
  that session printed or a platform limit named in tests/test_launch.py, and posts fit their platform's length.
- The claims are checked by claim-verifier into brand/launch/claims.json, pinned to the SHA-256 of the seven files.
- How the authorship is put in a post is John's call (state/NEEDS_JOHN.md in FIRE); the drafts leave it out.
- The five Product Hunt gallery images, brand/launch/ph-1.png to ph-5.png (1270 x 760, task RB5b), are built by
  brand/launch/gallery.py from the demo session (brand/demo/manifest.json), README lines and the promise above;
  one terminal size and one window across the set, Rewind on the one block each list item names. Look at
  brand/launch/gallery-sheet.png, then each image; the independent review is brand/launch/review.json and
  tests/test_gallery.py fails if an image changes after it.

## Logo direction brief (from RB1)

Concept: a **playhead on a step ruler**. A single vertical line (the playhead) crossing a row of evenly spaced
tick marks, with the line sitting one tick behind the last one. It reads as both a tape counter and a
timeline scrubbed back one step. The ticks are the chain of recorded calls; the playhead is where you
stepped back to.

- Must work as a one-colour mark at 16 px (favicon, terminal prompt glyph) and as a wordmark lockup.
- Geometry only: straight lines and one small left-pointing step, no arrows curling in a circle, no clock faces,
  no hourglass, no shield, no padlock, no chain-link icon.
- Colour: Reel on Leader, Leader on Reel, with Record or Rewind for the playhead only.
- Wordmark: "rewindagent" lowercase, Bricolage Grotesque 800, one word.
- Avoid: gradients, glow, sparkles, glass, 3D, mascot.
- Deliver later: SVG mark, wordmark, mono and reverse versions, and a 16 px check.

## Do

- Show real commands and real output; keep samples short.
- Say "planned" next to anything not built, every time.
- Use the step ruler (ticks with one playhead) as the single recurring motif.
- Left align text; let whitespace and a hairline rule do the structuring.
- Use Record or Rewind once per view, for the thing to look at.
- End pages with: made by John B Joseph

## Don't

- Don't claim more than the code does: a PyPI release, a live-session run of the Codex and Cursor hooks, and anything paid are still to come.
- Don't present it as a security, compliance or monitoring product.
- Don't use purple, violet, neon, gradients, glass, blobs, sparkles, emoji or stock robot imagery.
- Don't invent users, quotes, logos, stars, downloads, numbers or benchmarks.
- Don't use any word from "Words we never use".
- Don't centre every block; don't set body text in the accent colours.
