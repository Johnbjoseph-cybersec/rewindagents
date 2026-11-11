# rewindagent - brand identity

Status: identity (RB1, written by Iris Kapoor, Creative Studio) and logo set (RB2, see "Logo" below). No site yet.
Not self-graded; an independent reviewer scores it in brand/review.json.

## One-line promise

Ctrl+Z for AI coding agents: record, replay, rewind.

## Positioning

rewindagent is an open-source recorder for coding agents. It writes every tool call an agent makes
(Claude Code today; Codex and Cursor planned) into a tamper-evident, hash-chained JSONL log and saves a
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
   Example: "There is no pip package yet. Today you run it from a clone with PYTHONPATH."
3. **Calm.** Mistakes happen; we do not dramatise them.
   Example: "The agent deleted the wrong folder. Step back one."
4. **Dry.** One small joke at most, never at the reader's expense.
   Example: "Undo is a feature your editor has had for decades."
5. **Hands-on.** Commands and file paths over adjectives.
   Example: "Run python3 -m rewindagent verify and it names the first bad record."

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

## Logo (RB2)

Built by brand/logo/build.py (geometry + text outlined from the OFL font files) and rendered by
brand/logo/render.mjs (resvg). Look at brand/logo/contact-sheet.png: every asset, plus the mark at true 16, 32
and 64 px.

- Mark: four ticks on a two-unit rule, 16-unit grid, integer coordinates. A Record red playhead stands on the
  third tick: a bar crossing the rule, with a down-pointing marker one unit above it. The fourth tick, the
  step that was rewound, is solid Rule grey.
- One change from the brief below: the small left-pointing flag was dropped. Bar plus flag read as the
  digit 1, and the caps tried after it read as a pin or a T. A detached marker reads as a timeline cursor.
  The grey tick after the playhead carries "one step back".
- favicon.svg / favicon-32.png are a separate 16 px drawing: one tick, the playhead, the rewound tick in Tape.
- Files: logo-mark.svg (light), logo-mark-reverse.svg (dark), logo-mark-mono.svg (currentColor),
  logo-wordmark.svg / -reverse / -mono (horizontal), favicon.svg + favicon-32.png, avatar-512.png,
  logo-light.png and logo-dark.png (1024, stacked: mark over the name), social-preview-1280x640.png.
- Wordmark: Bricolage Grotesque 800, tracking -0.02 em, no kerning table applied. In the horizontal lockup
  the ruler is 1.25 x-heights tall and the text baseline is the bottom of the rule.

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

- Don't claim more than the code does: Codex and Cursor support, a pip package and anything paid are planned.
- Don't present it as a security, compliance or monitoring product.
- Don't use purple, violet, neon, gradients, glass, blobs, sparkles, emoji or stock robot imagery.
- Don't invent users, quotes, logos, stars, downloads, numbers or benchmarks.
- Don't use any word from "Words we never use".
- Don't centre every block; don't set body text in the accent colours.
