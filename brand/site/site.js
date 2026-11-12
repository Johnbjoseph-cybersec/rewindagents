/* rewindagents site: one local script, no libraries, nothing fetched (CSP: script-src 'self', connect-src 'none').
   The page is complete without it. It makes three things live:
   1. the hero player: the real demo session (data-session, computed by build.py from brand/demo/manifest.json)
      as a ruler you can drag, step with the arrow keys, play, and rewind;
   2. entrances: sections below the fold rise in once as they scroll into view;
   3. a copy button on every command panel.
   Every init is isolated, so a failure in one cannot cost the page another. Reduced motion: no autoplay, no
   entrances, the player still works by hand. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function safe(fn) { try { fn(); } catch (err) { if (window.console) console.warn("site.js:", err); } }

  /* ---- 1. the player ---------------------------------------------------------------------------------- */
  safe(function () {
    var root = document.getElementById("player");
    if (!root) return;
    var data = JSON.parse(root.getAttribute("data-session"));
    var steps = data.steps, max = steps.length - 1, good = data.good;
    var range = root.querySelector(".pl-range"), play = root.querySelector(".pl-play"), rew = root.querySelector(".pl-rewind");
    var count = root.querySelector(".pl-count b"), tool = root.querySelector(".pl-tool"), target = root.querySelector(".pl-target"),
        note = root.querySelector(".pl-note"), msg = root.querySelector(".pl-msg");
    var rows = {}, ticks = root.querySelectorAll(".tick");
    Array.prototype.forEach.call(root.querySelectorAll(".pl-files .f"), function (li) { rows[li.getAttribute("data-file")] = li; });
    var rewound = false, timer = null, shown = -1;

    function render(i, opts) {
      opts = opts || {};
      var s = steps[i], prev = shown >= 0 ? steps[shown] : null;
      count.textContent = String(i);
      tool.textContent = i === 0 ? "start" : s.tool;
      target.textContent = i === 0 ? "the project before the agent" : s.target;
      note.textContent = s.note ? " [" + s.note + "]" : "";
      data.files.forEach(function (f) {
        var li = rows[f], st = s.state[f];
        li.className = "f is-" + st + (opts.restored && prev && prev.state[f] !== st ? " flash" : "") +
          (!opts.restored && prev && prev.state[f] !== st && i > shown ? " pulse" : "");
        li.querySelector(".st").textContent = opts.restored && prev && prev.state[f] !== st ? "restored" : data.words[st];
      });
      Array.prototype.forEach.call(ticks, function (t) {
        var n = +t.getAttribute("data-n");
        t.classList.toggle("past", n <= i);
        t.classList.toggle("cur", n === i);
      });
      range.value = String(i);
      range.setAttribute("aria-valuetext", "step " + i + " of " + max + (i ? ": " + s.tool + " " + s.target : ""));
      root.classList.toggle("wrecked", Object.keys(s.state).some(function (k) { return s.state[k] === "gone"; }));
      shown = i;
    }
    function say(text) { msg.textContent = text; }
    function stop() { if (timer) { clearInterval(timer); timer = null; } root.classList.remove("playing"); }
    function describe(i) {
      if (rewound && i === good) return "Rewound: the files are back the way they were right after step " + good + ". " + data.undo;
      var gone = Object.keys(steps[i].state).filter(function (k) { return steps[i].state[k] === "gone"; });
      if (gone.length) return "Step " + i + ": " + gone.length + " test files are gone. Press rewind.";
      if (i === 0) return "Before the agent: five files, all unchanged.";
      return "Step " + i + " of " + max + ". Every file is saved before the agent changes it.";
    }
    function runTo(to, ms, done, restored) {
      stop();
      root.classList.add("playing");
      var dir = to >= shown ? 1 : -1;
      timer = setInterval(function () {
        if (shown === to) { stop(); if (done) done(); return; }
        var next = shown + dir;
        render(next, { restored: restored && next === to });
        say(describe(next));
      }, ms);
    }
    function doPlay() { rewound = false; render(0); say(describe(0)); runTo(max, reduce ? 0 : 420, function () { say(describe(max)); }); }
    function doRewind() {
      var from = shown;
      if (from <= good) { render(max); from = max; }
      root.classList.add("rewinding");
      rewound = true;
      runTo(good, reduce ? 0 : 160, function () {
        root.classList.remove("rewinding");
        render(good, { restored: false });
        // show what the rewind put back, against the wrecked step
        data.files.forEach(function (f) {
          if (steps[from].state[f] !== steps[good].state[f]) {
            rows[f].classList.add("flash");
            rows[f].querySelector(".st").textContent = "restored";
          }
        });
        say(describe(good));
      });
    }

    range.disabled = false; play.disabled = false; rew.disabled = false;
    root.classList.add("live");
    range.addEventListener("input", function () { stop(); rewound = false; render(+range.value); say(describe(+range.value)); });
    play.addEventListener("click", doPlay);
    rew.addEventListener("click", doRewind);
    Array.prototype.forEach.call(ticks, function (t) {
      t.addEventListener("click", function () { stop(); rewound = false; var n = +t.getAttribute("data-n"); render(n); say(describe(n)); });
    });
    render(max);

    // autoplay once, when the player is first on screen: play to the wreck, hold, rewind
    if (!reduce && "IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        if (!entries[0].isIntersecting) return;
        io.disconnect();
        setTimeout(function () {
          rewound = false; render(0); say(describe(0));
          runTo(max, 380, function () { say(describe(max)); setTimeout(function () { if (shown === max) doRewind(); }, 1400); });
        }, 600);
      }, { threshold: 0.5 });
      io.observe(root);
      ["pointerdown", "keydown"].forEach(function (ev) { root.addEventListener(ev, function () { io.disconnect(); }, { once: true }); });
    }
  });

  /* ---- 2. entrances ----------------------------------------------------------------------------------- */
  safe(function () {
    if (reduce || !("IntersectionObserver" in window)) return;
    var els = Array.prototype.filter.call(document.querySelectorAll("[data-reveal]"), function (el) {
      return el.getBoundingClientRect().top > window.innerHeight * 0.9;   // only what is still below the fold
    });
    els.forEach(function (el) { el.classList.add("pre"); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); en.target.classList.remove("pre"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (el) { io.observe(el); });
  });

  /* ---- 3. copy buttons -------------------------------------------------------------------------------- */
  safe(function () {
    if (!navigator.clipboard) return;
    Array.prototype.forEach.call(document.querySelectorAll("pre.term"), function (pre) {
      var cmds = Array.prototype.map.call(pre.querySelectorAll(".l"), function (l) { return l; })
        .filter(function (l) { return l.firstElementChild && l.firstElementChild.classList.contains("p"); })
        .map(function (l) { return l.textContent.replace(/^\$ /, ""); });
      if (!cmds.length || pre.closest(".session")) return;     // the session panels are a record, not commands to run
      var b = document.createElement("button");
      b.type = "button"; b.className = "copy"; b.textContent = "Copy";
      b.setAttribute("aria-label", "Copy " + (cmds.length > 1 ? cmds.length + " commands" : "the command"));
      b.addEventListener("click", function () {
        navigator.clipboard.writeText(cmds.join("\n")).then(function () {
          b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1600);
        });
      });
      pre.classList.add("has-copy");
      pre.appendChild(b);
    });
  });

  /* ---- header shadow line once the page scrolls ------------------------------------------------------ */
  safe(function () {
    var top = document.querySelector(".top");
    if (!top) return;
    var on = function () { top.classList.toggle("stuck", window.scrollY > 8); };
    window.addEventListener("scroll", on, { passive: true }); on();
  });
})();
