# Bold round gate (branch site/magic, 2026-11-18)

| check | result |
|---|---|
| console errors / warnings (1440, 834, 390, both recordings) | 0 |
| horizontal overflow, scrollLeft (1440, 834, 390) | 0, 0 |
| elements left under opacity 0.9 after a full scroll | 0 |
| ScrollTriggers without an end | 0 |
| CLS, Lighthouse mobile x3 / desktop x2 | 0 / 0 |
| CLS across the 1440 and 390 scroll recordings (layout-shift observer) | 0, 0 |
| Lighthouse mobile perf / a11y / bp / seo | 92, 92, 91 / 100 / 100 / 92 |
| Lighthouse desktop | 100 / 100 / 100 / 92 |
| reduced motion | no GSAP, no pin, stage is the built still: 22 rows + 6 files visible, 0 faded |
| keyboard | Stop reachable by Tab (11th stop), focus ring 2px solid, Enter stops on the still |
| tests | 741 run, OK, 24 skipped |
| recordings | scroll-1440.mp4 58.6 fps, scroll-390.mp4 55.7 fps, real time from screencast timestamps |

SEO 92 is the localhost robots.txt check; BEFORE and the previous round score the same.
The 390 recording's one 1.9 s frame gap is the 3 s hold on a static first screen (the screencast sends frames only on repaint).
Changed test facts: test_hero_replay_shows_only_the_session_and_never_moves_the_page replaced by
test_hero_stage_is_the_recorded_session_and_never_moves_the_page; test_counters_are_counted_from_the_repository added;
a comment in test_site_js_adds_only_the_motion_files_and_only_after_first_paint documents the stage exception.
Review: round 1 8.0 (review-round1.txt); fixes applied; round 2 pending.
