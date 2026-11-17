/* rewindagents site motion. Local only: GSAP 3.13 (vendor/), nothing from another origin (CSP script-src 'self',
   connect-src 'none'). The page is complete without this file, and the first screen paints without waiting for it.
   GSAP is progressive enhancement: its three files are added after the load event, when the browser is idle (or at
   the first scroll, touch or key), and only content still below the fold is animated, so nothing already on screen
   moves or shifts. Every block is isolated: one failure cannot cost the page another.
   Signature moves: the hero stage plays the recorded session and, pinned, scrubs it with the scroll both ways; each
   section's top rule is swept right to left by a playhead (a rewind); scrolling back up fast "rewinds" the page. */
(function () {
  "use strict";
  var root = document.documentElement;
  var here = document.currentScript && document.currentScript.src;      // site.js's own URL: vendor/ sits beside it
  var VENDOR = ["vendor/gsap.min.js", "vendor/ScrollTrigger.min.js", "vendor/SplitText.min.js"];
  var reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  function safe(name, fn) { try { fn(); } catch (err) { if (window.console) console.warn("site.js " + name + ":", err); } }
  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function fmt(t) { t = Math.max(0, Math.round(t)); return Math.floor(t / 60) + ":" + ("0" + (t % 60)).slice(-2); }

  /* ---- the film: custom ruler controls over the native video (native controls stay without scripts) ---- */
  safe("film", function () {
    var film = $("#film"); if (!film) return;
    var video = $(".film-video", film), play = $(".film-play", film), bar = $(".film-bar", film);
    var ruler = $(".film-ruler", film), fill = $(".film-fill", film), time = $(".film-time", film);
    var total = parseFloat(film.getAttribute("data-total")) || 90;
    var ticks = $$(".ft", film), chapters = $$(".ft.ch", film), now = $(".film-now", film), fs = $(".film-fs", film);
    video.controls = false; play.hidden = false; bar.hidden = false;
    ticks.forEach(function (t) { t.style.left = (parseFloat(t.getAttribute("data-t")) / total * 100) + "%"; });
    var track = video.textTracks && video.textTracks[0];
    if (track) track.mode = "hidden";     // the captions are burnt into the picture; the track stays for assistive tech
    function sync() {
      var t = video.currentTime || 0, d = video.duration || total;
      fill.style.width = (t / d * 100) + "%";
      time.textContent = fmt(t) + " / " + fmt(d);
      ruler.setAttribute("aria-valuenow", String(Math.round(t)));
      ticks.forEach(function (k) { k.classList.toggle("past", parseFloat(k.getAttribute("data-t")) <= t); });
      var cur = null; chapters.forEach(function (k) { if (parseFloat(k.getAttribute("data-t")) <= t + 0.05) cur = k; });
      var label = cur ? (chapters.indexOf(cur) + 1) + " / " + chapters.length + "  " + cur.getAttribute("data-title") : "";
      if (now.textContent !== label) now.textContent = label;
    }
    function theatre(on) { root.classList.toggle("theatre", on); }
    function start() {
      film.classList.add("playing"); theatre(true);
      var r = film.querySelector(".film-frame").getBoundingClientRect();
      if (r.top < 0 || r.bottom > window.innerHeight) film.querySelector(".film-frame").scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      video.muted = false;
      var p = video.play(); if (p && p.catch) p.catch(function () { video.muted = true; video.play(); });
    }
    play.addEventListener("click", start);
    video.addEventListener("click", function () { if (video.paused) start(); else video.pause(); });
    video.addEventListener("pause", function () { film.classList.remove("playing"); film.classList.add("paused"); theatre(false); });
    video.addEventListener("play", function () { film.classList.add("playing"); film.classList.remove("paused", "ended"); });
    video.addEventListener("ended", function () { theatre(false); film.classList.remove("playing"); film.classList.add("ended"); $(".film-play-label", film).textContent = "Watch again"; });
    video.addEventListener("timeupdate", sync);
    function seekAt(x) {
      var r = ruler.getBoundingClientRect(), f = Math.min(1, Math.max(0, (x - r.left) / r.width));
      if (video.readyState === 0) { video.preload = "auto"; video.load(); }
      video.currentTime = f * (video.duration || total); sync();
    }
    ruler.addEventListener("click", function (ev) { seekAt(ev.clientX); if (video.paused) start(); });
    if (fs) fs.addEventListener("click", function () {
      var el = film.querySelector(".film-frame");
      if (document.fullscreenElement) document.exitFullscreen(); else if (el.requestFullscreen) el.requestFullscreen();
      if (video.paused) start();
    });
    ruler.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        ev.preventDefault();
        video.currentTime = Math.max(0, Math.min(video.duration || total, (video.currentTime || 0) + (ev.key === "ArrowRight" ? 5 : -5)));
        sync();
      } else if (ev.key === " " || ev.key === "Enter") { ev.preventDefault(); if (video.paused) start(); else video.pause(); }
    });
    // stop the film when it scrolls out of view, so it never talks over the page
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (en) { if (!en[0].isIntersecting && !video.paused) video.pause(); }, { threshold: 0.2 }).observe(video);
    }
  });

  /* ---- copy buttons on command panels ---------------------------------------------------------------- */
  safe("copy", function () {
    if (!navigator.clipboard) return;
    $$("pre.term").forEach(function (pre) {
      if (pre.closest(".session") || pre.closest(".stage")) return;     // a record of a session, not commands to run
      var file = pre.classList.contains("file");                              // a file to paste (the workflow yaml): every line
      var cmds = $$(".l", pre).filter(function (l) { return file || (l.firstElementChild && l.firstElementChild.classList.contains("p")); })
        .map(function (l) { return l.textContent.replace(/^\$ /, ""); });
      if (!cmds.length) return;
      var b = document.createElement("button");
      b.type = "button"; b.className = "copy"; b.textContent = "Copy";
      b.setAttribute("aria-label", file ? "Copy the file" : cmds.length > 1 ? "Copy " + cmds.length + " commands" : "Copy the command");
      b.addEventListener("click", function () {
        navigator.clipboard.writeText(cmds.join("\n")).then(function () {
          b.textContent = "Copied"; b.classList.add("done"); pre.classList.remove("copied"); void pre.offsetWidth; pre.classList.add("copied");
          setTimeout(function () { b.textContent = "Copy"; b.classList.remove("done"); pre.classList.remove("copied"); }, 1600);
        });
      });
      pre.classList.add("has-copy"); pre.appendChild(b);
    });
  });

  /* ---- header line once the page moves ------------------------------------------------------------- */
  safe("header", function () {
    var top = $(".top"); if (!top) return;
    var on = function () { top.classList.toggle("stuck", window.scrollY > 8); };
    window.addEventListener("scroll", on, { passive: true }); on();
  });

  /* ---- motion, after first paint: the vendor files in order, then motion() ----------------------------- */
  if (reduce || !here) return;
  var asked = false;
  function loadMotion() {
    if (asked) return;
    asked = true;
    var n = 0;
    (function next() {
      if (n === VENDOR.length) { safe("motion", start); return; }
      var tag = document.createElement("script");
      tag.src = new URL(VENDOR[n++], here).href;
      tag.onload = next;
      document.head.appendChild(tag);
    })();
  }
  // both the load event and the first contentful paint, as the browser reports it: on a light page the load event
  // comes before the first paint, so it alone is not "after first paint". Then the next idle moment.
  var gates = 2;
  function pass() { if (--gates === 0) (window.requestIdleCallback || function (fn) { setTimeout(fn, 300); })(loadMotion, { timeout: 2500 }); }
  if (document.readyState === "complete") pass(); else window.addEventListener("load", pass, { once: true });
  try {
    var painted = false;
    var po = new PerformanceObserver(function (list) {
      if (!painted && list.getEntriesByName("first-contentful-paint").length) { painted = true; po.disconnect(); pass(); }
    });
    po.observe({ type: "paint", buffered: true });
  } catch (err) { setTimeout(pass, 1000); }
  ["scroll", "pointerdown", "keydown"].forEach(function (ev) { window.addEventListener(ev, loadMotion, { once: true, passive: true }); });

  function start() {
    if (!window.gsap || !window.ScrollTrigger) return;
    gsap.registerPlugin(ScrollTrigger); if (window.SplitText) gsap.registerPlugin(SplitText);
    var fontsReady = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
    fontsReady.then(function () { motion(); ScrollTrigger.refresh(); });
  }
  // only what the reader has not reached yet: anything on screen, or scrolled past, stays exactly where it is
  function below(el) { return el.getBoundingClientRect().top > window.innerHeight; }

  function motion() {
  var EASE = "expo.out", SNAP = "power4.inOut";
  var wide = window.matchMedia("(min-width: 961px)").matches, fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ---- 1. the hero stage ------------------------------------------------------------------------------
     One function draws the session at a position p: 0..N the steps play (rows, files, the ruler's playhead), N..N+1
     the damage holds, N+1..N+2 the rewind is typed and the playhead runs back, N+2..N+3 the restore rows tick in and
     the deleted files fly back from the terminal, N+3..N+4 the still. Every word comes from the page: rows are shown
     and hidden by visibility, tags read from the rows' data attributes. Autoplay (with Stop) while the stage is on
     screen; pinned, the scroll drives p both ways. */
  safe("stage", function () {
    var box = $("#stage"); if (!box) return;
    var pin = $(".stage-pin", box), pre = $("pre.term", box), at = $(".st-at", box), slot = $(".st-ctl", box) || $(".st-head", box);
    var rows = $$(".l", pre);
    var cmds = rows.filter(function (r) { var s = $(".sel", r); return s && !s.children.length; });
    if (cmds.length !== 2) return;
    var i1 = rows.indexOf(cmds[1]), steps = rows.slice(1, i1), after = rows.slice(i1 + 1), N = steps.length, END = N + 4;
    var words = cmds.map(function (r) { return $(".sel", r).textContent; }), still = at.textContent;
    var ticks = $$(".sr-tk", box), phw = $(".sr-phw", box), fill = $(".sr-fill", box), struck = $$(".x", pre);
    var good = ticks.map(function (t) { return t.classList.contains("at"); }).indexOf(true) + 1;
    var wFrom = ticks.map(function (t) { return t.classList.contains("w"); }).indexOf(true) + 1;
    if (good < 1 || wFrom < 1) return;
    var files = $$(".ff", box).map(function (li) {
      return { li: li, tag: $(".ftg", li), born: +li.getAttribute("data-born"), gone: +li.getAttribute("data-gone"),
               back: +li.getAttribute("data-back"), still: li.getAttribute("data-still"),
               touch: (li.getAttribute("data-touch") || "").split(",").filter(Boolean).map(function (t) { var k = t.split(":"); return [+k[0], k[1]]; }) };
    });
    var cur = $(".rp-cur") || document.createElement("span"); cur.className = "rp-cur"; cur.setAttribute("aria-hidden", "true");
    function clamp(v) { return Math.max(0, Math.min(1, v)); }
    function cls(el, c, on) { if (el.classList.contains(c) !== on) el.classList.toggle(c, on); }
    function text(el, t) { if (el.textContent !== t) el.textContent = t; }
    function ease(v) { return v < 0.5 ? 2 * v * v : 1 - Math.pow(-2 * v + 2, 2) / 2; }
    files.forEach(function (f) { f.li.classList.remove("back"); });
    box.classList.add("live");
    var typed = -1;
    function render(p) {
      var s = Math.min(N, Math.floor(p + 1e-6)), rw = clamp(p - N - 1);
      var head = p <= N ? p : p < N + 1 ? N : N - (N - good) * ease(rw);
      var x = Math.max(0, head - 0.5) / N;
      phw.style.transform = "translateX(" + (x * 100).toFixed(3) + "%)";
      fill.style.transform = "scaleX(" + x.toFixed(4) + ")";
      var undone = p >= N + 1.5, landed = p >= N + 2;
      ticks.forEach(function (t, j) {
        var k = j + 1;
        cls(t, "past", k <= head + 1e-6);
        cls(t, "hitw", k >= wFrom && k <= s && !undone);
        cls(t, "undone", k >= wFrom && undone);
        cls(t, "home", k === good && landed);
      });
      steps.forEach(function (r, j) {
        var k = j + 1;
        cls(r, "off", k > s);
        cls(r, "cur", k === s && k < wFrom && p < N);
        cls(r, "wreck", k >= wFrom && k <= s && !undone);
      });
      struck.forEach(function (el) { cls(el, "on", undone); });
      cls(cmds[1], "off", p < N + 1);
      var n = p < N + 1 ? 0 : Math.round(words[1].length * clamp((p - N - 1) / 0.45));
      if (n !== typed) {
        typed = n;
        var sel = $(".sel", cmds[1]); sel.textContent = words[1].slice(0, n);
        if (n < words[1].length && p >= N + 1) sel.appendChild(cur);
      }
      after.forEach(function (r, j) { cls(r, "off", p < N + 2 + j * 0.16); });
      text(at, p < 1 ? words[0].split(" ").pop() : p < N + 1 ? "step " + s : still);
      var shift = wide ? 1 : 0;
      files.forEach(function (f) {
        var tb = f.back >= 0 ? N + 2 + f.back * 0.16 : Infinity, back = p >= tb, fb = clamp((p - tb) / 0.4);
        var last = null; f.touch.forEach(function (t) { if (t[0] <= s) last = t; });
        var gone = f.gone > 0 && s >= f.gone && !back;
        cls(f.li, "off", s < f.born && !back);
        cls(f.li, "gone", gone);
        cls(f.li, "wreck", !back && !!last && last[0] >= wFrom);
        cls(f.li, "hot", !back && !!last && last[0] === s && p - s < 0.8 && p < N);
        cls(f.li, "home", back && fb >= 1);
        cls(f.li, "fly", back && fb < 1);
        text(f.tag, back ? f.still : last ? last[1] + " " + last[0] : "");
        var tx = 0, ty = 0;
        if (back) { var e = 1 - Math.pow(1 - fb, 3); if (shift) tx = (1 - e) * 220; }  // phone: rows stack tight, so a file coming back changes colour in place
        else if (f.born > 0 && s >= f.born) tx = 28 * (1 - clamp((p - f.born) / 0.35));
        var tr = tx || ty ? "translate(" + tx.toFixed(1) + "px," + ty.toFixed(1) + "px)" : "";
        if (f.li.style.transform !== tr) f.li.style.transform = tr;
      });
    }

    // autoplay: the tape runs back from the still, the session plays, the rewind lands, hold; three passes
    var r0 = box.getBoundingClientRect();
    var A = { p: END }, S = { p: END }, scrubbing = false, stopped = false, inView = r0.top < window.innerHeight && r0.bottom > 0, done = false;
    var auto = gsap.timeline({ paused: true, repeat: 2, repeatDelay: 3, onUpdate: function () { if (!scrubbing) render(A.p); },
                               onComplete: function () { done = true; label(false); } });
    auto.to(A, { p: 0, duration: 0.9, ease: "power2.inOut" })
        .to(A, { p: N, duration: N * 0.36, ease: "none" })
        .to(A, { p: N + 1, duration: 0.9, ease: "none" })
        .to(A, { p: N + 2, duration: 1.1, ease: "power1.inOut" })
        .to(A, { p: N + 3, duration: 1.3, ease: "none" })
        .to(A, { p: END, duration: 0.3, ease: "none" });
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "copy rp-btn";
    function label(playing) { btn.textContent = playing ? "Stop" : "Replay"; btn.setAttribute("aria-label", playing ? "Stop the replay" : "Play the replay again"); }
    function chase(p, d) { gsap.to(S, { p: p, duration: d, ease: "power3.out", overwrite: true, onUpdate: function () { render(S.p); } }); }
    function play() { if (stopped || done || scrubbing || !inView) return; auto.play(); label(true); }
    btn.addEventListener("click", function () {
      if (auto.isActive() || (!stopped && !done && !scrubbing)) { stopped = true; auto.pause(); label(false); S.p = A.p; chase(END, 0.6); }
      else { stopped = false; done = false; scrubbing = false; auto.restart(); label(true); }
    });
    slot.appendChild(btn); label(true);
    ScrollTrigger.create({ trigger: box, start: "top bottom", end: "bottom top",
      onToggle: function (self) { inView = self.isActive; if (!inView) auto.pause(); else play(); } });

    // the pin: only if the reader has not reached the stage yet, so the space it adds is never above them
    var top = $(".top"), offset = top && getComputedStyle(top).position === "sticky" ? top.offsetHeight + 8 : 0;
    // pinned in the middle of the free screen, so the paper above and below it is even
    var room = window.innerHeight - offset, mid = offset + Math.max(0, Math.round((room - pin.offsetHeight) / 2));
    var pinTop = pin.getBoundingClientRect().top + window.scrollY - mid;
    if (pin.offsetHeight <= room && window.scrollY < pinTop - 4) {
      ScrollTrigger.create({ trigger: pin, start: "top " + mid + "px", end: "+=" + (wide ? 2200 : 1500), pin: true, anticipatePin: 1,
        onToggle: function (self) { if (self.isActive) { scrubbing = true; auto.pause(); S.p = A.p; } },
        onUpdate: function (self) { if (self.isActive) { scrubbing = true; chase(Math.min(END, self.progress * (END + 0.8)), 0.5); } },
        onLeave: function () { scrubbing = false; chase(END, 0.4); },
        onLeaveBack: function () {
          scrubbing = false;
          if (!stopped && !done) { A.p = S.p; auto.play(0.9 + Math.max(0, S.p) * 0.36); label(true); } else chase(END, 0.5);
        } });
    }
    render(END);
    play();
  });

  /* ---- 2. section heads: the ruler's playhead scrubs into place, the heading rises word by word ------- */
  safe("heads", function () {
    $$(".sec .label").filter(below).forEach(function (lab) {
      var head = lab.nextElementSibling && lab.nextElementSibling.classList.contains("head") ? lab.nextElementSibling : null;
      var h2 = head && $("h2", head), lede = head && $(".lede", head);
      var playhead = $(".ruler path", lab);
      var tl = gsap.timeline({ paused: true, defaults: { ease: EASE } });
      // the cut: a playhead runs the section's top rule right to left (a rewind), drawing ticks behind it
      var sec = lab.closest(".sec"), sw = document.createElement("div");
      sw.className = "sweep"; sw.setAttribute("aria-hidden", "true");
      ["sw-line", "sw-tk", "sw-phw"].forEach(function (c) { var k = document.createElement("span"); k.className = c; sw.appendChild(k); });
      var ph = document.createElement("span"); ph.className = "sw-ph"; sw.lastChild.appendChild(ph);
      sec.insertBefore(sw, sec.firstChild);
      tl.to($(".sw-phw", sw), { xPercent: -100, duration: 0.9, ease: SNAP }, 0)
        .to($(".sw-line", sw), { scaleX: 1, duration: 0.9, ease: SNAP }, 0)
        .fromTo($(".sw-tk", sw), { clipPath: "inset(0 0 0 100%)" }, { clipPath: "inset(0 0 0 0%)", duration: 0.9, ease: SNAP }, 0)
        .to(sw, { opacity: 0, duration: 0.5, ease: "power2.out" }, 1.0);
      if (playhead) tl.from(playhead, { x: 70, duration: 0.9, ease: SNAP }, 0.05);
      tl.from($$("span", lab), { opacity: 0, x: 10, duration: 0.45, stagger: 0.05 }, 0.12);
      if (h2) {
        var words = window.SplitText ? new SplitText(h2, { type: "words", mask: "words" }).words : [h2];
        tl.from(words, { yPercent: 110, duration: 0.7, stagger: 0.025 }, 0.12);
      }
      if (lede) {
        var lines = window.SplitText ? new SplitText(lede, { type: "lines", mask: "lines", aria: "none" }).lines : [lede];
        tl.from(lines, { yPercent: 100, duration: 0.7, stagger: 0.05 }, 0.3);
      }
      // locked to the scroll position: the cut and the heading are complete before the heading passes ~two thirds
      // of the screen, at any scroll speed, and they run back if the reader scrolls back up past the cut
      ScrollTrigger.create({ trigger: sec, start: "clamp(top bottom)", end: "clamp(top 50%)", scrub: 0.3, animation: tl });
    });
  });

  /* ---- 2b. terminals and the screenshot wipe in right to left (the rewind direction) ------------------- */
  safe("wipes", function () {
    // locked to the scroll position, not to time: at any scroll speed a panel is whole before it reaches mid-screen
    $$(".sec pre.term, .sec .shot img").filter(below).forEach(function (el) {
      gsap.fromTo(el, { clipPath: "inset(-24px -24px -24px 100%)" }, { clipPath: "inset(-24px -24px -24px 0%)", ease: "power2.out",
        scrollTrigger: { trigger: el, start: "clamp(top bottom)", end: "clamp(top 74%)", scrub: 0.35 } });
    });
  });

  /* ---- 2c. counters count up from zero the first time they are seen (the built number is the fallback) -- */
  safe("counts", function () {
    $$(".cnt").filter(below).forEach(function (k) {
      var end = parseInt(k.getAttribute("data-to"), 10), obj = { v: 0 };
      if (!(end > 0)) return;
      k.textContent = "0";
      ScrollTrigger.create({ trigger: k, start: "top 98%", once: true, onEnter: function () {
        gsap.to(obj, { v: end, duration: Math.min(1.3, 0.6 + end / 1000), ease: "power3.out", onUpdate: function () { k.textContent = String(Math.round(obj.v)); } });
      } });
    });
  });

  /* ---- 2d. desktop: terminals drift against the scroll; the agent row slides with it ------------------------ */
  safe("parallax", function () {
    if (!wide) return;
    $$(".sec pre.term").filter(function (p) { return !p.closest(".session"); }).forEach(function (p) {
      gsap.fromTo(p, { y: 22 }, { y: -22, ease: "none", scrollTrigger: { trigger: p, start: "top bottom", end: "bottom top", scrub: 0.8 } });
    });
    var strip = $(".hero .agents ul");  // the marks drift into the free space right of the row; the label and rule stay on the grid
    if (strip && window.innerWidth >= 1200) gsap.fromTo(strip, { x: 0 }, { x: 64, ease: "none", scrollTrigger: { start: 0, end: 900, scrub: 0.6 } });
  });

  /* ---- 2e. pointer devices: primary buttons lean to the pointer; terminals tilt a little under it ------- */
  safe("pointer", function () {
    if (!fine) return;
    $$(".btn-primary").forEach(function (b) {
      var qx = gsap.quickTo(b, "x", { duration: 0.45, ease: "power3.out" }), qy = gsap.quickTo(b, "y", { duration: 0.45, ease: "power3.out" });
      b.addEventListener("pointermove", function (ev) { var r = b.getBoundingClientRect(); qx((ev.clientX - r.left - r.width / 2) * 0.18); qy((ev.clientY - r.top - r.height / 2) * 0.3); });
      b.addEventListener("pointerleave", function () { qx(0); qy(0); });
    });
    $$(".sec pre.term, .hero-install pre.term").forEach(function (p) {
      gsap.set(p, { transformPerspective: 1200 });
      var rx = gsap.quickTo(p, "rotationX", { duration: 0.5, ease: "power3.out" }), ry = gsap.quickTo(p, "rotationY", { duration: 0.5, ease: "power3.out" });
      p.addEventListener("pointermove", function (ev) { var r = p.getBoundingClientRect(); ry(((ev.clientX - r.left) / r.width - 0.5) * 2.4); rx(-((ev.clientY - r.top) / r.height - 0.5) * 2.4); });
      p.addEventListener("pointerleave", function () { rx(0); ry(0); });
    });
  });

  /* ---- 3. rows and tiles arrive by row ---------------------------------------------------------------- */
  safe("rows", function () {
    var groups = [".gap > li", ".trio > div", ".shot", ".session > div", ".cols > div", ".steps > li", ".ledger > li", ".cmdrow", ".plan", ".faq details", ".walk > li", ".doc > section"];
    groups.forEach(function (sel) {
      var els = $$(sel).filter(below); if (!els.length) return;
      els.forEach(function (el) {
        gsap.fromTo(el, { y: 46, opacity: 0 }, { y: 0, opacity: 1, ease: "power2.out",
          scrollTrigger: { trigger: el, start: "clamp(top bottom)", end: "clamp(top 80%)", scrub: 0.3 } });
      });
    });
    // the ledger's numbers count up from zero the first time they are seen
    $$(".ledger .k").filter(below).forEach(function (k) {
      var m = k.textContent.match(/^([\d,]+)(.*)$/); if (!m) return;
      var end = parseInt(m[1].replace(/,/g, ""), 10), obj = { v: 0 };
      ScrollTrigger.create({ trigger: k, start: "top 90%", once: true, onEnter: function () {
        gsap.to(obj, { v: end, duration: 1.4, ease: "power3.out", onUpdate: function () { k.textContent = Math.round(obj.v).toLocaleString("en-US") + m[2]; } });
      } });
    });
  });

  /* ---- 4. the film: grows from an inset card to the full width as it comes up the page --------------- */
  safe("film-scroll", function () {
    var frame = $(".film-frame"); if (!frame || !below(frame)) return;
    gsap.fromTo(frame, { clipPath: "inset(0 8% round 24px)" }, {
      clipPath: "inset(0 0% round 0px)", ease: "none",
      scrollTrigger: { trigger: "#film", start: "top 95%", end: "top 20%", scrub: 0.6 }
    });
    if ($(".film-play")) gsap.from(".film-play", { scale: 0.6, opacity: 0, duration: 1, ease: "back.out(1.6)", clearProps: "transform,opacity",
      scrollTrigger: { trigger: "#film", start: "top 60%", once: true } });
  });

  /* ---- 5. closing band: the headline slams in, the command types ------------------------------------- */
  safe("close", function () {
    var c = $(".close"); if (!c || !below(c)) return;
    var h = $("h2", c), chars = window.SplitText ? new SplitText(h, { type: "chars,words" }).chars : [h];
    var tl = gsap.timeline({ paused: true });
    tl.from(chars, { yPercent: 100, opacity: 0, duration: 0.8, stagger: 0.014, ease: "expo.out" })
      .from($$(".btn, pre", c), { y: 20, opacity: 0, duration: 0.7, stagger: 0.1, ease: EASE }, 0.35);
    ScrollTrigger.create({ trigger: c, start: "clamp(top bottom)", end: "clamp(top 55%)", scrub: 0.3, animation: tl });
  });

  /* ---- 6. the tape: scroll progress as the brand ruler; scrolling back up fast is a rewind ------------ */
  safe("tape", function () {
    var tape = document.createElement("div");
    tape.className = "tape"; tape.setAttribute("aria-hidden", "true");
    var bar = document.createElement("span"); bar.className = "tape-bar"; tape.appendChild(bar);
    // one tick per numbered section, where it starts on the page; the playhead in Record runs along them
    var secs = $$(".sec .label").map(function (l) { return l.closest(".sec"); });
    var tks = secs.map(function () { var k = document.createElement("span"); k.className = "tape-tk"; tape.appendChild(k); return k; });
    var ph = document.createElement("span"); ph.className = "tape-ph"; tape.appendChild(ph);
    var marks = [];
    function place() {
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      marks = secs.map(function (s, j) {
        var p = Math.min(1, Math.max(0, (s.getBoundingClientRect().top + window.scrollY - window.innerHeight * 0.3) / max));
        tks[j].style.left = (p * 100) + "%"; return p;
      });
    }
    place(); ScrollTrigger.addEventListener("refresh", place);
    var tag = document.createElement("span"); tag.className = "tape-tag"; tag.textContent = "◂◂ rewinding"; tape.appendChild(tag);
    document.body.appendChild(tape);
    var skewEls = $$(".sec .head h2, .hero h1");
    var skew = skewEls.length ? gsap.quickTo(skewEls, "skewX", { duration: 0.5, ease: "power3.out" }) : function () {};
    var off = null;
    ScrollTrigger.create({
      start: 0, end: "max",
      onUpdate: function (self) {
        bar.style.transform = "scaleX(" + self.progress.toFixed(4) + ")";
        ph.style.transform = "translateX(" + (self.progress * (tape.clientWidth - 3) + 1).toFixed(1) + "px)";
        marks.forEach(function (p, j) { tks[j].classList.toggle("past", p <= self.progress + 0.0005); });
        var v = self.getVelocity();
        if (v < -900) {
          tape.classList.add("rew"); root.classList.add("rewinding");
          skew(Math.max(-9, v / 450));
          clearTimeout(off);
          off = setTimeout(function () { tape.classList.remove("rew"); root.classList.remove("rewinding"); skew(0); }, 260);
        }
      }
    });
  });

  }
})();
