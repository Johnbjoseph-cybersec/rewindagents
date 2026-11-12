/* rewindagents site motion. Local only: GSAP 3.13 (vendor/), nothing fetched (CSP script-src/connect-src).
   The page is complete without this file. Every block is isolated: one failure cannot cost the page another.
   Signature move: scrolling back up fast "rewinds" the page (the tape at the top runs red, headings skew back). */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduce = !root.classList.contains("js-motion");
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
      var cmds = $$(".l", pre).filter(function (l) { return l.firstElementChild && l.firstElementChild.classList.contains("p"); })
        .map(function (l) { return l.textContent.replace(/^\$ /, ""); });
      if (!cmds.length) return;
      var b = document.createElement("button");
      b.type = "button"; b.className = "copy"; b.textContent = "Copy";
      b.setAttribute("aria-label", cmds.length > 1 ? "Copy " + cmds.length + " commands" : "Copy the command");
      b.addEventListener("click", function () {
        navigator.clipboard.writeText(cmds.join("\n")).then(function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1600); });
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

  if (reduce || !window.gsap || !window.ScrollTrigger) { root.classList.add("motion-ready"); return; }
  gsap.registerPlugin(ScrollTrigger); if (window.SplitText) gsap.registerPlugin(SplitText);
  var fontsReady = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
  fontsReady.then(function () { motion(); });
  function motion() {
  var EASE = "expo.out", SNAP = "power4.inOut";

  /* ---- 1. hero intro: the promise sets in line by line, then the terminal prints the real session ---- */
  safe("hero", function () {
    var hero = $(".hero"); if (!hero) return;
    var tl = gsap.timeline({ paused: true, defaults: { ease: EASE } });
    var h1 = $("h1", hero), lines = [h1];
    if (window.SplitText) { lines = new SplitText(h1, { type: "lines,words", mask: "lines", linesClass: "h1-line" }).lines; }
    root.classList.add("motion-ready");
    tl.from($(".eyebrow", hero), { y: 16, opacity: 0, duration: 0.7 })
      .from(lines, { yPercent: 110, duration: 1.1, stagger: 0.09 }, 0.1)
      .from($(".lede", hero), { y: 24, opacity: 0, duration: 0.9 }, 0.55)
      .from($$(".cta .btn", hero), { y: 18, opacity: 0, duration: 0.7, stagger: 0.08 }, 0.7)
      .from($$(".agents .ag-label, .agents .ag", hero), { y: 14, opacity: 0, duration: 0.6, stagger: 0.07, clearProps: "transform" }, 0.95);
    var panel = $(".hero-panel .panel", hero);
    if (panel) {
      var rows = $$(".l", panel);
      tl.fromTo(panel, { clipPath: "inset(0 0 100% 0 round 6px)" }, { clipPath: "inset(0 0 0% 0 round 6px)", duration: 0.9, ease: SNAP }, 0.35)
        .from(rows, { opacity: 0, x: -10, duration: 0.25, stagger: 0.07, ease: "power2.out" }, 0.9)
        .add(function () { panel.classList.add("lit"); }, ">-0.1");
    }
    tl.from($$(".hero-panel .caption, .hero-panel .facts li", hero), { y: 12, opacity: 0, duration: 0.6, stagger: 0.05 }, 1.6);
    tl.play();
  });

  /* ---- 2. section heads: the ruler's playhead scrubs into place, the heading rises word by word ------- */
  safe("heads", function () {
    $$(".sec .label").forEach(function (lab) {
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
    var groups = [".trio > div", ".shot", ".session > div", ".cols > div", ".steps > li", ".ledger > li", ".cmdrow", ".plan", ".faq details", ".walk > li", ".doc > section"];
    groups.forEach(function (sel) {
      var els = $$(sel); if (!els.length) return;
      gsap.set(els, { y: 46, opacity: 0 });
      ScrollTrigger.batch(els, {
        start: "top 90%", once: true,
        onEnter: function (b) { gsap.to(b, { y: 0, opacity: 1, duration: 0.95, stagger: 0.09, ease: EASE, overwrite: true }); }
      });
    });
    // the ledger's numbers count up from zero the first time they are seen
    $$(".ledger .k").forEach(function (k) {
      var m = k.textContent.match(/^([\d,]+)(.*)$/); if (!m) return;
      var end = parseInt(m[1].replace(/,/g, ""), 10), obj = { v: 0 };
      ScrollTrigger.create({ trigger: k, start: "top 90%", once: true, onEnter: function () {
        gsap.to(obj, { v: end, duration: 1.4, ease: "power3.out", onUpdate: function () { k.textContent = Math.round(obj.v).toLocaleString("en-US") + m[2]; } });
      } });
    });
  });

  /* ---- 4. the film: grows from an inset card to the full width as it comes up the page --------------- */
  safe("film-scroll", function () {
    var frame = $(".film-frame"); if (!frame) return;
    gsap.fromTo(frame, { clipPath: "inset(0 8% round 24px)" }, {
      clipPath: "inset(0 0% round 0px)", ease: "none",
      scrollTrigger: { trigger: "#film", start: "top 95%", end: "top 20%", scrub: 0.6 }
    });
    if ($(".film-play")) gsap.from(".film-play", { scale: 0.6, opacity: 0, duration: 1, ease: "back.out(1.6)", clearProps: "transform,opacity",
      scrollTrigger: { trigger: "#film", start: "top 60%", once: true } });
  });

  /* ---- 5. closing band: the headline slams in, the command types ------------------------------------- */
  safe("close", function () {
    var c = $(".close"); if (!c) return;
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
    var tag = document.createElement("span"); tag.className = "tape-tag"; tag.textContent = "◂◂ rewinding"; tape.appendChild(tag);
    document.body.appendChild(tape);
    var skewEls = $$(".sec .head h2, .hero h1");
    var skew = skewEls.length ? gsap.quickTo(skewEls, "skewX", { duration: 0.5, ease: "power3.out" }) : function () {};
    var off = null;
    ScrollTrigger.create({
      start: 0, end: "max",
      onUpdate: function (self) {
        bar.style.transform = "scaleX(" + self.progress.toFixed(4) + ")";
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

  window.addEventListener("load", function () { ScrollTrigger.refresh(); });
  }
})();
