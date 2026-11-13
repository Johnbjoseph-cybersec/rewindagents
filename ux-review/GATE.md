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
