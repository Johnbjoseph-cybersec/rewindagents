# Site magic pass (branch site/magic), 2026-11-18: gate numbers

BEFORE = main at fbf38e4, served from `git archive`; AFTER = this branch, `brand/site/build.py`.

| Gate | BEFORE | AFTER |
|---|---|---|
| Console errors/warnings, 1440 / 834 / 390 (`tools/fullpage.mjs`) | 0 / 0 / 0 | 0 / 0 / 0 |
| Horizontal overflow (scrollWidth - clientWidth) | 0 / 0 / 0 | 0 / 0 / 0 (a 6 px phone overflow was found and fixed) |
| Elements left under opacity 0.9 after a full scroll | 0 | 0 |
| ScrollTriggers with no end | 0 | 0 |
| Layout change while the hero replay plays (`tools/heroframes.mjs`, >1 px on h1, panel, install, strip, next section) | n/a | 0 of 34 frames (1440), 0 of 30 (390) |
| Reduced motion: replay, button, hidden rows, GSAP | n/a | none, none, 0, not loaded |
| Stop leaves the built still (rows hidden, strikes, label) | n/a | 0 hidden, 2 struck, "rewind 12" |
| Lighthouse mobile index (perf / a11y / bp / seo), 2 runs | 96 / 100 / 100 / 92, twice | 96 and 95 / 100 / 100 / 92 |
| Lighthouse desktop index, 2 runs | 100 / 100 / 100 / 92, twice | 100 / 100 / 100 / 92, twice |
| CLS (Lighthouse, all runs) | 0 | 0 |
| Test suite | 738 OK, 24 skipped | 740 OK, 24 skipped |

SEO 92 is the same on both: a localhost serve, not a page change. Mobile LCP 2,702 ms on both, one AFTER sample 2,852 ms.

Not verified: Safari and Firefox, real phones, the published site.

Review (cs-iris-kapoor, read-only, 2 rounds): `review-round1.txt` 8.4, `review-round2.txt` 8.7. Round 2's one row
under 8 (mobile 7.8) was a stalled 390 replay in the frame strip. It was the capture: element screenshots under mobile
emulation take the panel out of view, which pauses the pass. Re-recorded with the DevTools screencast
(`tools/herocast.mjs`, `cast-390/sheet.png`), it plays in full. The replay now also returns to the still whenever the
panel leaves the screen, so a half-drawn panel cannot be left behind. Round-2 fixes 3 to 5 were applied after the
round. No third round was run (the limit was two).
