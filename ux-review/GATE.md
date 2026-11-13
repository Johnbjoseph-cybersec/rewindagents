# Gate, pass 4: go-live fixes (2026-11-13)

John approved go-live with two fixes first: Lighthouse mobile >= 95 on index, pricing and docs (pass 3: 86 / 94 / 92),
and a shorter "01 Fork and compare". Measured on the committed build of `course/proving-ground` the same way as pass 3:
`python3 brand/site/build.py`, served uncompressed by `python3 -m http.server`, headless Chrome with a fresh
`--user-data-dir` per run. Layout, links, select: `ux-review/tools/gate.mjs` (`gate.json`, motion on;
`gate-reduced.json`, `REDUCED=1`). Lighthouse 12.2.1, three runs per page and preset: `ux-review/lighthouse/pass4-*.json`.

## Result: PASS on every line

| Check | Bar | Measured |
|---|---|---|
| Console errors | 0 | 0 on 18 renders (3 pages x 1440, 834, 390, motion on and reduced) |
| Failed requests | 0 | 0 (lazy images forced to load; all 8 poster sizes in the srcsets answer 200) |
| Horizontal overflow at 390 | 0 px | 0 px on all three pages (also 0 at 834 and 1440) |
| Elements past the right edge | 0 | 0; 9 (index) and 24 (docs) spans at 390 sit inside terminal panels that scroll sideways on purpose, as in pass 3 |
| Overlapping text blocks | 0 | 0 on all 18 renders |
| Clipped boxes | 0 unintended | Reduced motion: 0 except `.film-play-label` at 390 (visually hidden by design). Motion on: 61 on index (62 at 390) and 3 on pricing are GSAP SplitText word masks on below-the-fold headings, unchanged from pass 3 |
| Layout shift | CLS 0 | 0 in all 18 Lighthouse runs; 0 in 18 more loads of index at 1440, 1350 and 834 with a layout-shift observer, and 0 while scrolling every page top to bottom with GSAP arriving |
| No script | page complete | with JavaScript off: hero, ledes, panels, film (native controls) and poster all visible |
| Local links and assets | all | 66 of 66 resolve (anchors checked against ids on the target page) |
| In-page anchors | all | 22 of 22 |
| External links | all | 11 of 13 answer 200 to `curl -L`. `tests/test_runs.py` and `tests/test_runs_demo.py` on GitHub `main` are 404 until this branch is merged and pushed (same as pass 3) |
| One-click select | the command, without `$` | exactly `pipx install git+https://github.com/Johnbjoseph-cybersec/rewindagents` at 1440, 834 and 390, motion on and off |
| Lighthouse accessibility | >= 95 | 100 on all 18 runs |
| Lighthouse performance, desktop | >= 95 | 100 / 100 / 100 (index, pricing, docs), all runs |
| Lighthouse performance, mobile | >= 95 | **96 / 99 / 98** (index, pricing, docs), the same in each of the three runs |
| Suite | only the known failure | `python3 -m unittest discover -s tests`: 622 run, 1 failure, 22 skipped. The failure is `test_vsl` claim review (`claims-verified.json` BLOCK until publishing), as before |

## Lighthouse, per page (three runs each; the runs agreed except index mobile LCP 2.6 / 2.6 / 2.7 s)

| Page | Preset | Perf | A11y | BP | SEO | FCP | LCP | CLS | TBT | pass 3 perf |
|---|---|---|---|---|---|---|---|---|---|---|
| index.html | mobile | 96 | 100 | 100 | 92 | 1.7 s | 2.6 s | 0 | 20 ms | 86 |
| index.html | desktop | 100 | 100 | 100 | 92 | 0.4 s | 0.6 s | 0 | 0 ms | 100 |
| pricing.html | mobile | 99 | 100 | 100 | 92 | 1.1 s | 2.2 s | 0 | 0 ms | 94 |
| pricing.html | desktop | 100 | 100 | 100 | 92 | 0.3 s | 0.5 s | 0 | 0 ms | 100 |
| docs/ | mobile | 98 | 100 | 100 | 92 | 1.2 s | 2.3 s | 0 | 0 ms | 92 |
| docs/ | desktop | 100 | 100 | 100 | 92 | 0.3 s | 0.5 s | 0 | 0 ms | 100 |

SEO 92 is still `robots-txt` (the local server answers it with a 404 page), not a site defect. The server sends
no compression; GitHub Pages does, so these are the pessimistic numbers.

## What moved the numbers (each measured alone on a copy before it went in)

- GSAP off the page (125 KB): site.js adds the three vendor files after both the load event and the browser's
  first-contentful-paint entry, then an idle moment (or at the first scroll, touch or key). The load event alone
  was not enough: on pricing and docs it fires before the first paint, and GSAP was still counted (94 / 94).
- Film poster: a lazy `<picture>` under the video, AVIF/WebP at 480/960/1440/1920 (a phone takes 7 to 14 KB).
- No script before first paint: `flag.js` gone, the hero intro is CSS (FCP 2.4 s -> 2.0 s on index). Its rise
  is transform-only: with a fade, Chrome recorded the LCP when the fade ended (1.25 s observed) and index fell to 89.
- Commit Mono cut to the latin range (48 -> 21 KB a weight, all OpenType features kept): index 93 -> 95/96.
- `site.min.css` (53 -> 42 KB; renders pixel-identical to `site.css` on all three pages at 1440 and 390).
- Hanken 600 preloaded: the hero's ghost button changing width on the font swap was the only layout shift.

Motion kept: section heads, row reveals, the ledger count, the film's clip reveal, the closing band and the
rewind tape, for everything still below the fold when GSAP arrives. Dropped: the GSAP hero intro (line-by-line
h1, terminal print-in), replaced by a short CSS rise; anything already on screen when GSAP arrives stays put.

## Copy: "01 Fork and compare"

"Fork any recorded step" and "Compare the runs" are two sentences each (`FORK_SHORT`, `COMPARE_SHORT` in
build.py), and the section ends with a link to `docs/#fork`. The docs page still carries the README's full
sentences word for word; the README is unchanged.

## Renders

`ux-review/final/after-index-1440.png`, `after-index-390.png` changed (pricing and docs re-rendered byte-identical).
Launch shots: all five re-rendered; only `launch-assets/shot-2-fork-1440.png` (the changed section) is replaced.
shot-1 and shot-5 came out byte-identical; shot-3 and shot-4 differed only in antialiasing (0.03% and 0% of pixels),
so the committed ones stay. Cards and clips do not show the section and were not touched.

---

# Gate, pass 3: the proving-ground course (2026-11-13)

Measured on the committed build of branch `course/proving-ground` (`python3 brand/site/build.py`), served with
`python3 -m http.server`, in headless Chrome with fresh `--user-data-dir` profiles. Layout, links and the select
probe: `ux-review/tools/gate.mjs`, raw output `ux-review/gate.json` (motion on; the site address is written `<site_url>`, as the repo keeps it in config.json only) and `ux-review/gate-reduced.json`
(`REDUCED=1`, prefers-reduced-motion). Lighthouse 12.2.1: `ux-review/lighthouse/course-*.json`, with `main`'s
committed pages (`git archive main brand/site`, same assets) measured the same way as the baseline.

## Result: PASS on every line except Lighthouse mobile performance (not met, and not met on main either)

| Check | Bar | Measured |
|---|---|---|
| Console errors | 0 | 0 on 9 renders (index, pricing, docs at 1440, 834, 390), motion on and off |
| Failed requests | 0 | 0 |
| Horizontal overflow at 390 | 0 px | 0 px on all three pages (also 0 at 834 and 1440) |
| Elements past the right edge | 0 | 0. At 390, 9 (index) and 24 (docs) spans sit inside terminal panels that scroll sideways on purpose (`overflow-x: auto`, the panel itself inside the page); gate.mjs now counts these apart as `inScroller` |
| Overlapping text blocks | 0 | 0 on all 18 renders |
| Clipped boxes | 0 unintended | Reduced motion: 0, except `.film-play-label` at 390, a visually hidden label by design (clip-path inset 50%). Motion on: 61 + 4 on index and 3 on pricing are GSAP SplitText line/word masks from `site.js` (unchanged from main); a settled motion render at 1440 shows every descender whole |
| Local links and assets | all | 61 of 61 resolve (anchors checked against ids on the target page) |
| In-page anchors | all | 22 of 22 |
| External links | all | 11 of 13 answer 200 to `curl -L`. `tests/test_runs.py` and `tests/test_runs_demo.py` on GitHub `main` are 404 until this branch is merged and pushed (the Tested section cites them) |
| One-click select | the command, without `$` | the hero click selects exactly `pipx install git+https://github.com/Johnbjoseph-cybersec/rewindagents` at 1440, 834 and 390 (with motion, after the 1.5 s entrance settles) |
| Lighthouse accessibility | >= 95 | 100 on all six runs |
| Lighthouse performance, desktop | >= 95 | 100 / 100 / 100 (index, pricing, docs) |
| Lighthouse performance, mobile | >= 95 | **86 / 94 / 92: not met.** main measured the same way: 83 / 89 / 92 |
| Suite | green | `python3 -m unittest discover -s tests`: 596 run, 1 failure, 22 skipped. The failure is `test_vsl` claim review: `brand/vsl/claims-verified.json` is BLOCK on main too and clears only after publishing |
| Words | no em dash, no section sign | enforced by `tests/test_site.py`; 0 em dashes in the pages, README and BRAND.md |

## Lighthouse, per run

| Page | Preset | Branch perf | a11y | BP | SEO | FCP | LCP | CLS | TBT | main perf |
|---|---|---|---|---|---|---|---|---|---|---|
| index.html | mobile | 86 | 100 | 100 | 92 | 2.3 s | 3.8 s | 0.001 | 80 ms | 83 |
| index.html | desktop | 100 | 100 | 100 | 92 | 0.5 s | 0.8 s | 0.007 | 0 ms | 100 |
| pricing.html | mobile | 94 | 100 | 100 | 92 | 1.5 s | 3.1 s | 0 | 0 ms | 89 |
| pricing.html | desktop | 100 | 100 | 100 | 92 | 0.4 s | 0.6 s | 0 | 0 ms | 100 |
| docs/ | mobile | 92 | 100 | 100 | 92 | 1.7 s | 3.2 s | 0 | 0 ms | 92 |
| docs/ | desktop | 100 | 100 | 100 | 92 | 0.4 s | 0.6 s | 0 | 0 ms | 100 |

SEO 92 everywhere is `robots-txt`: the local server answers `/robots.txt` with a 404 page. Not a site defect.

## Why mobile performance is short, and what it would take (John's call)

Pass 2 measured 98 on the original look. main's hybrid look (2026-11-12) added the film poster (122 KB, fetched
at load even with `preload="none"`) and GSAP + ScrollTrigger + SplitText (125 KB). Lighthouse's mobile
simulation counts every byte requested before the first large paint, and on localhost that is all of them.
Measured on copies of this build: without the poster 88; without the three GSAP files and the poster 92; the
first-paint bytes left (fonts, a 53 KB stylesheet, a 58 KB page) keep LCP near 3.0 s. Reaching 95 needs the
poster and motion scripts to load after first paint, which `site.js` is built not to do ("loads and parses
nothing", `tests/test_site.py`), or a lighter first screen. That changes main's approved motion, so it is left
for John. A phone-only skip of the hero intro was tried and changed nothing (LCP 3.8 s), so it was reverted.

## Not measured here

- Real devices; Chrome's 390 px emulation is the only phone.
- The published site: it still serves the pre-course pages (v0.0.7, original look).

---

# Gate, pass 2 (2026-11-13)

Measured on the committed build (`python3 brand/site/build.py`), served locally with `python3 -m http.server`,
in headless Google Chrome with its own `--user-data-dir` (not the chrome-devtools MCP).

- Layout, links and the select probe: `ux-review/tools/gate.mjs`, raw output in `ux-review/gate.json`.
- Lighthouse 12.2.1, mobile (default throttling) and desktop presets: summaries in `ux-review/lighthouse/`.

## Result: PASS on every line

| Check | Bar | Measured |
|---|---|---|
| Console errors | 0 | 0 on 9 renders (index, pricing, docs at 1440, 834, 390) |
| Failed requests (4xx/5xx/failed), lazy images forced to load | 0 | 0 |
| Horizontal overflow at 390 | 0 px | 0 px on all three pages (also 0 at 834 and 1440); 0 elements past the right edge |
| Overlapping text blocks (h1-h3, p, li, a, pre, img, figcaption, summary, rulers; closed answers excluded) | 0 | 0 on all 9 renders |
| Clipped boxes (overflow hidden/clip with content larger than the box) | 0 | 0 |
| Local links and assets resolve | all | 56 of 56 return 200 (page anchors checked against ids on the target page) |
| In-page anchors | all | 14 of 14 point at an existing id |
| External links | all | 11 of 11 answer 200 to `curl -L`: the repository, LICENSE, the five cited test files, the waitlist issue form, the site's own canonical URLs |
| Cited tests exist | all | 13 of 13 test functions found in `tests/` (the build checks) and in the files on GitHub `main` |
| One-click select | the command, without `$` | a click on the hero command selects exactly `pipx install git+https://github.com/Johnbjoseph-cybersec/rewindagents` at 1440, 834 and 390 |
| Lighthouse accessibility | >= 95 | 100 on all six runs |
| Lighthouse performance | >= 95 | 98 / 100 (index mobile / desktop), 98 / 100 (pricing), 99 / 100 (docs) |
| Site tests | green | `tests/test_site.py` 12 of 12; full suite `python3 -m unittest discover -s tests`: 297 run, 0 failures, 10 skipped (installed-binary tests) |
| Words | no em dash, no section sign, no banned word | enforced by `tests/test_site.py` on every page; no em dash added in copy |

## Lighthouse, per run

| Page | Preset | Perf | A11y | Best practices | SEO | LCP | CLS | TBT |
|---|---|---|---|---|---|---|---|---|
| index.html | mobile | 98 | 100 | 100 | 100 | 2.3 s | 0 | 0 ms |
| index.html | desktop | 100 | 100 | 100 | 100 | 0.5 s | 0 | 0 ms |
| pricing.html | mobile | 98 | 100 | 100 | 100 | 2.2 s | 0 | 0 ms |
| pricing.html | desktop | 100 | 100 | 100 | 100 | 0.5 s | 0 | 0 ms |
| docs/ | mobile | 99 | 100 | 100 | 100 | 2.0 s | 0 | 0 ms |
| docs/ | desktop | 100 | 100 | 100 | 100 | 0.5 s | 0 | 0 ms |

Two fixes came out of the first Lighthouse run, both in this pass:
- pricing `heading-order` (98): the plan cards were h3 directly under the page's h1. `plans()` now takes the
  heading level: h2 on the pricing page, h3 on the landing page. A first desktop re-run still read the cached
  old page from a shared profile; with a fresh profile it is 100 (`lighthouse/pricinghtml-desktop.json`).
- index mobile performance 95 (LCP 2.5 s): the three faces of the first screen are now preloaded; 98, LCP 2.3 s.

## Not measured here

- Real devices. Chrome's 390 px emulation is the only phone in this gate.
- The clip GIF's paused first frame (AUDIT F13) is a content issue, not a gate line.
