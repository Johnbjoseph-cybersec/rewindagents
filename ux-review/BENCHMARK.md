# Benchmark: what the best dev-tool sites do in the first 30 seconds

Read 2026-11-13. Short fetches only (title, h1, og:image, whether an install line and a copy control are in the
markup). Where a note is a design observation and not a fetched fact, it says so.

| Site | First screen (fetched h1) | Install line in the hero | Copy control | Proof | og:image |
|---|---|---|---|---|---|
| Bun | "Bun is a fast JavaScript runtime & toolkit. All in one." | yes: `curl -fsSL https://bun.sh/install \| bash`, with npm and brew tabs | yes ("Copy" in markup) | benchmark bar charts right under the hero, each with the command that produced it | dedicated share image |
| Warp | "The software factory infrastructure platform" | yes: `curl -fsSL .../agent-cli \| bash` | yes | product screenshot in the hero | dedicated `/og/default.png` |
| Raycast | "Your shortcut to everything." | download button (app, not CLI) | yes | the product UI itself, at full size | generated per page |
| Linear | "The product development system for teams and agents" | no (SaaS sign-up) | yes | real product UI, in-page | generated per page (`/api/og`) |
| Vercel | "Agentic Infrastructure" | no (deploy button) | yes | logos + live UI | dedicated |
| Supabase | "Build in a weekend Scale to millions" | no (dashboard sign-up) | none in the home markup | code samples, per framework | dedicated |
| Zed | "Your last next editor" | download button | none in the home markup | the editor, rendered | dedicated (webp) |
| Stripe docs | "Documentation" | per-page, in a code block | yes, on every code block | the API call and its real response, side by side | dedicated |

## The five patterns that matter for rewindagents

1. **The first screen states the job in one line and shows the product doing it.** Every one of the eight puts
   the real product (a UI, an editor, a command and its output) next to or right under the h1. For a CLI the
   product is a terminal, so the hero is a terminal, not an illustration. rewindagents already does this; the
   panel should tell the whole story (the wreck, then the rewind) in one look.
2. **The install line is on the first screen, as text you can copy.** Bun and Warp, the two CLI-first sites,
   put `curl ... | bash` in the hero with a copy control. A visitor who has decided should not have to scroll.
   rewindagents has an "Install" button that scrolls to a section; the command itself is below the fold at
   1440 and three screens down at 390.
3. **Proof is specific and checkable.** Bun's benchmarks name the command that produced each bar; Stripe shows
   the real response next to the request. Nothing is "trusted by thousands". For an open-source tool with no
   users yet, the checkable proof is the test suite: name the test behind each claim.
4. **One share image per page, made for the 1.91:1 crop.** All eight ship a dedicated og:image. A link pasted
   into LinkedIn, Slack or X is the first impression for most visitors; it should read at thumbnail size (a
   few words, one big shape), not be a shrunk screenshot.
5. **Mobile is the same story, re-stacked, not cut.** (Design observation.) The best sites keep the h1, the
   install line and one proof element on the phone's first two screens; code blocks wrap or scroll inside
   themselves and never widen the page.

## What we deliberately do NOT take from them

- Dark hero bands, gradients, glow, animated backgrounds, logo walls, scroll-triggered motion: John rejected
  this direction for rewindagents on 2026-11-12 (abcadd0, reverted in baf5d02).
- Social-proof numbers (stars, users, downloads): none exist yet, and the site test forbids them.
- A JavaScript copy button: the site's promise and `tests/test_site.py` say "no scripts" (only the JSON-LD
  block). The scriptless equivalent is a command that selects whole on one click (`user-select: all`), so
  click + Cmd/Ctrl+C copies exactly the command and never the `$` prompt. See AUDIT.md F2.
