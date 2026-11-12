# vendor/

- `gsap.min.js`, `ScrollTrigger.min.js`, `SplitText.min.js`: GSAP 3.13.0, copied unmodified from the npm package
  `gsap@3.13.0` (`dist/`), source-map comments removed. Licence: GreenSock "Standard no-charge license",
  https://gsap.com/standard-license (free to use and redistribute, including commercial use).
- `flag.js`: ours. Adds `js-motion` to `<html>` before first paint unless reduced motion is requested.

Served from the site itself; the pages' Content-Security-Policy allows scripts from 'self' only.
