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
Review: round 1 8.0 (review-round1.txt); fixes applied in 3a5c3a2.

## Round 2 (cs-iris-kapoor, the last allowed review)
Recordings and key frames regenerated after the round-1 fixes (frames/k1440-*.png, k390-*.png, sheets), looked at
frame by frame. Round 2: 8.3 (review-round2.txt). Rows: identity 9.0, hero 8.2, stage 8.3, transitions 8.0,
counters 8.4, type/grid 8.5, mobile 7.9, premium 8.3. Below the bar (9.0, no row under 8).
Its ranked fixes applied once, then re-recorded (no round 3 review: cap reached):
- hero: a later `gap: 0` reset zeroed the hero grid gutter from 1200 px; the install panel now shares the left edge
  of the second paragraph and the buttons (815 -> 841 px, measured).
- stage: struck rows no longer slide 14 px left of the grid; filled tags centre their word (whole chips).
- 390: stage terminal on the 16 px page margin; tree at 11 px so "test_timeout.py" + its tag fit the 174 px column
  (measured: name ends 307, tag starts 314); a file coming back changes colour in place (the 48 px fly overlapped
  the row under it mid-flight).
- counters finish faster (<= 1.3 s, start at 98% of the viewport); "0" was already static.
Not fixed (residual, honest): terminal mostly empty before step ~11 (height is fixed for CLS 0); ~90 px of paper
above the pinned stage at 1440 (centred pin); film control bar under the poster card (predates this round);
desktop stage feeling, hero first screen still static type apart from the stage autoplay below it.
After the fixes: recordings 59.3 / 55.8 fps, CLS 0 / 0, 0 errors; fullpage gate 1440/834/390: overflow 0,
scrollLeft 0, faded 0, triggers without end 0, errors 0; Lighthouse mobile x3 93/94/93, a11y 100, bp 100, seo 92,
CLS 0; desktop x2 100/100/100/92, CLS 0.0000003; tests 741 OK (24 skipped).
