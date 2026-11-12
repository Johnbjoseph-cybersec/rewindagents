# vendor/

- `gsap.min.js`, `ScrollTrigger.min.js`, `SplitText.min.js`: GSAP 3.13.0, copied unmodified from the npm package
  `gsap@3.13.0` (`dist/`), source-map comments removed. Licence: GreenSock "Standard no-charge license",
  https://gsap.com/standard-license (free to use and redistribute, including commercial use).
- `flag.js`: ours. Adds `js-motion` to `<html>` before first paint unless reduced motion is requested.

Served from the site itself; the pages' Content-Security-Policy allows scripts from 'self' only.
- `logos/claude-code.svg`, `logos/cursor.svg`: brand glyphs from Simple Icons 16.35.0 (CC0-1.0, https://simpleicons.org),
  unmodified. The marks remain trademarks of their owners and are shown only to say which agents rewindagents has
  a hook for. Codex is shown by name: Simple Icons no longer carries an OpenAI mark, so we do not use one.
  A logo joins the strip only when that agent's hook exists and is tested (tests/test_site.py checks the list
  against src/rewindagents/agents.py).
