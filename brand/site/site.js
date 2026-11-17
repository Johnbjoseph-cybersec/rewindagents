/* rewindagents site motion. Local only: GSAP 3.13 (vendor/), nothing from another origin (CSP script-src 'self',
   connect-src 'none'). The page is complete without this file, and the first screen paints without waiting for it.
   GSAP is progressive enhancement: its three files are added after the load event, when the browser is idle (or at
   the first scroll, touch or key), and only content still below the fold is animated, so nothing already on screen
   moves or shifts. Every block is isolated: one failure cannot cost the page another.
   Signature move: scrolling back up fast "rewinds" the page (the tape at the top runs red, headings skew back). */
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
      if (pre.closest(".session") || pre.closest(".hero-panel")) return;     // a record of a session, not commands to run
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
    safe("replay", replay);
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

  /* ---- the hero replay: the session behind the panel plays itself, then holds the still -----------------------
     Runs after first paint (with the motion files), never with reduced motion, only while the panel is on screen.
     Every line it shows is a line already in the panel: rows are hidden and shown again (visibility only, so nothing
     on the page moves), the two commands are typed back to their own text, and the elided "..." row shows the steps
     it stands for, which build.py put there from the same recorded session. Stop ends it on the still. */
  function replay() {
    var box = $("#replay"); if (!box) return;
    var pre = $("pre.term", box), svg = $(".ruler.live", box), at = $(".tl-at", box);
    if (!pre || !svg || !at) return;
    var rows = $$(".l", pre), gap = $(".rp-gap", pre);
    var cmds = rows.filter(function (r) { var s = $(".sel", r); return s && !s.children.length; });
    if (cmds.length !== 2 || !gap) return;
    var ticks = $$(".rp-tk", gap), dots = $(".c", gap);
    var i0 = rows.indexOf(gap), i1 = rows.indexOf(cmds[1]);
    var steps = rows.slice(i0 + 1, i1), after = rows.slice(i1 + 1);
    var struck = $$(".x", pre), wreck = steps.filter(function (r) { return $(".x", r); });
    var still = at.textContent, words = cmds.map(function (r) { return $(".sel", r).textContent; });
    // the ruler: the playhead path moves; ticks and rule left of it in ink, right of it in the rewound colour
    var home = +svg.getAttribute("data-at"), x0 = +svg.getAttribute("data-x0"), pitch = +svg.getAttribute("data-pitch");
    var ink = svg.getAttribute("data-ink"), dim = svg.getAttribute("data-after"), W = +svg.getAttribute("width");
    var head = $("path", svg), base = $$("rect", svg).filter(function (r) { return r.getAttribute("height") === "1"; });
    var marks = $$("rect", svg).filter(function (r) { return r.getAttribute("height") === "5"; });
    function playhead(k) {
      var px = x0 + (k - 1) * pitch;
      head.style.transform = "translateX(" + ((k - home) * pitch) + "px)";
      base[0].setAttribute("width", px.toFixed(1)); base[1].setAttribute("x", px.toFixed(1)); base[1].setAttribute("width", (W - px).toFixed(1));
      marks.forEach(function (m) { m.setAttribute("fill", +m.getAttribute("x") + 0.5 <= px + 0.01 ? ink : dim); });
    }
    function show(r, on) { r.classList.toggle("off", !on); }
    var cursor = document.createElement("span"); cursor.className = "rp-cur"; cursor.setAttribute("aria-hidden", "true");
    function type(r, n, w) { var sel = $(".sel", r); sel.textContent = w.slice(0, n); sel.appendChild(cursor); }
    function untype(r, w) { $(".sel", r).textContent = w; }
    function tick(k) { ticks.forEach(function (t, j) { t.hidden = j !== k; }); dots.hidden = k >= 0; }

    // one pass, as [ms, action]: the tape runs back, the session plays, the rewind lands, then a hold on the still
    var T = [], t = 0, c, k;
    function when(ms, fn) { T.push([ms, fn]); }
    rows.slice().reverse().forEach(function (r, j) { when(j * 30, function () { show(r, false); r.classList.remove("land", "lit"); }); });
    when(0, function () { at.textContent = "rewind"; struck.forEach(function (x) { x.classList.remove("on"); }); });
    for (k = home; k >= 1; k--) (function (k, j) { when(j * 34, function () { playhead(k); }); })(k, home - k);
    t = 420;
    when(t, function () { show(cmds[0], true); type(cmds[0], 0, words[0]); at.textContent = "step 1"; });
    for (c = 1; c <= words[0].length; c++) (function (c) { when(t + 60 + c * 34, function () { type(cmds[0], c, words[0]); }); })(c);
    t += 60 + words[0].length * 34 + 220;
    when(t, function () { untype(cmds[0], words[0]); show(gap, true); });
    ticks.forEach(function (_, j) { when(t + j * 105, function () { tick(j); playhead(j + 1); at.textContent = "step " + (j + 1); }); });
    t += ticks.length * 105;
    steps.forEach(function (r, j) {
      var n = ticks.length + 1 + j, slow = wreck.indexOf(r) >= 0;
      when(t, function () { if (j === 0) tick(-1); show(r, true); if (slow) r.classList.add("land"); playhead(n); at.textContent = "step " + n; });
      t += slow ? 420 : 240;
    });
    t += 420;
    when(t, function () { show(cmds[1], true); type(cmds[1], 0, words[1]); });
    for (c = 1; c <= words[1].length; c++) (function (c) { when(t + 60 + c * 38, function () { type(cmds[1], c, words[1]); }); })(c);
    t += 60 + words[1].length * 38 + 260;
    var last = ticks.length + steps.length;
    when(t, function () { untype(cmds[1], words[1]); at.textContent = still; });
    for (k = last - 1; k >= home; k--) (function (k, j) { when(t + j * 170, function () { playhead(k); }); })(k, last - 1 - k);
    t += (last - home) * 170 + 60;
    when(t, function () { struck.forEach(function (x) { x.classList.add("on"); }); });
    t += 380;
    after.forEach(function (r, j) { when(t + j * 150, function () { show(r, true); if ($(".hit", r)) r.classList.add("lit"); }); });
    t += after.length * 150;
    var LOOP = t + 3600, LOOPS = 3;
    T.sort(function (a, b) { return a[0] - b[0]; });

    function settle() {      // the still, exactly as built
      tick(-1);
      rows.forEach(function (r) { show(r, true); r.classList.remove("land", "lit"); });
      cmds.forEach(function (r, j) { untype(r, words[j]); });
      struck.forEach(function (x) { x.classList.add("on"); });
      playhead(home); at.textContent = still; pre.classList.remove("rp");
    }
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "copy rp-btn";
    function label(playing) { btn.textContent = playing ? "Stop" : "Replay"; btn.setAttribute("aria-label", playing ? "Stop the replay" : "Play the replay again"); }
    pre.appendChild(btn);

    var running = false, seen = false, el = 0, next = 0, loop = 0, prev = 0;
    function frame(now) {
      if (!running) return;
      var live = seen && !document.hidden;      // off screen, the pass waits where it is
      if (live) el += Math.min(64, now - prev);
      prev = now;
      while (live && next < T.length && T[next][0] <= el) T[next++][1]();
      if (el >= LOOP) {
        if (++loop >= LOOPS) { stop(); return; }
        el = 0; next = 0;
      }
      requestAnimationFrame(frame);
    }
    function play() { running = true; loop = 0; el = 0; next = 0; pre.classList.add("rp", "played"); label(true); prev = performance.now(); requestAnimationFrame(frame); }
    function stop() { running = false; settle(); label(false); }
    btn.addEventListener("click", function () { if (running) stop(); else play(); });
    if ("IntersectionObserver" in window) {
      // off screen the panel goes back to the still, never a half-drawn pass; back on screen the pass starts over
      new IntersectionObserver(function (en) {
        seen = en[0].isIntersecting;
        if (!running) return;
        if (!seen) { settle(); el = 0; next = 0; } else pre.classList.add("rp");
      }, { threshold: 0.5 }).observe(pre);
    } else seen = true;
    play();
  }

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

  /* ---- 2. section heads: the ruler's playhead scrubs into place, the heading rises word by word ------- */
  safe("heads", function () {
    $$(".sec .label").filter(below).forEach(function (lab) {
      var head = lab.nextElementSibling && lab.nextElementSibling.classList.contains("head") ? lab.nextElementSibling : null;
      var h2 = head && $("h2", head), lede = head && $(".lede", head);
      var playhead = $(".ruler path", lab);
      var tl = gsap.timeline({ paused: true, defaults: { ease: EASE } });
      if (playhead) tl.from(playhead, { x: -70, duration: 1.2, ease: SNAP }, 0);
      tl.from($$("span", lab), { opacity: 0, x: -8, duration: 0.6, stagger: 0.08 }, 0.15);
      if (h2) {
        var words = window.SplitText ? new SplitText(h2, { type: "words", mask: "words" }).words : [h2];
        tl.from(words, { yPercent: 105, duration: 0.95, stagger: 0.04 }, 0.2);
      }
      if (lede) tl.from(lede, { y: 22, opacity: 0, duration: 0.9 }, 0.45);
      ScrollTrigger.create({ trigger: lab, start: "top 86%", once: true, onEnter: function () { tl.play(); } });
    });
  });

  /* ---- 3. rows and tiles arrive by row ---------------------------------------------------------------- */
  safe("rows", function () {
    var groups = [".gap > li", ".trio > div", ".shot", ".session > div", ".cols > div", ".steps > li", ".ledger > li", ".cmdrow", ".plan", ".faq details", ".walk > li", ".doc > section"];
    groups.forEach(function (sel) {
      var els = $$(sel).filter(below); if (!els.length) return;
      gsap.set(els, { y: 46, opacity: 0 });
      ScrollTrigger.batch(els, {
        start: "top 90%", once: true,
        onEnter: function (b) { gsap.to(b, { y: 0, opacity: 1, duration: 0.95, stagger: 0.09, ease: EASE, overwrite: true }); }
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
    ScrollTrigger.create({ trigger: c, start: "top 75%", once: true, onEnter: function () { tl.play(); } });
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
