/* rewindagents: runs before first paint (blocking, 1 line of work). Marks the page as motion-capable unless the
   visitor asked for reduced motion. CSS hides only the intro elements under .js-motion, and a CSS failsafe shows
   them after 2.5 s even if site.js never runs, so a script failure can never leave a blank page. */
(function () { try { if (!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) document.documentElement.classList.add("js-motion"); } catch (e) {} })();
