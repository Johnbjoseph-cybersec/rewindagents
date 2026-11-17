// A real-time scroll-through recording of a whole page, as the browser paints it (DevTools screencast, no
// screenshot calls). Holds on the first screen, then scrolls with an instant scrollTo in a rAF loop, slower through a
// pinned scene (the reader's own pace there), and writes an mp4 whose frame durations are the screencast's own
// timestamps, so the clip runs in real time. Also reports layout shifts and frame gaps seen while recording.
// usage: NODE_PATH=... node scrollcast.mjs <baseUrl> <out.mp4> [width=1440] [pxPerSec=1100] [holdMs=3000] [pinPxPerSec=550]
import { createRequire } from "module";
import path from "path";
import fs from "fs";
import { execFileSync } from "child_process";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [base, out, w = "1440", speed = "1100", hold = "3000", pinSpeed = "550"] = process.argv.slice(2);
const width = +w, mobile = width < 500, height = mobile ? 844 : 900, dpr = mobile ? 2 : 1;
const dir = out.replace(/\.mp4$/, "") + "-frames";
fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", args: ["--no-first-run", "--hide-scrollbars"],
});
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(e.message));
await page.emulate({ viewport: { width, height, deviceScaleFactor: dpr, isMobile: mobile, hasTouch: mobile },
  userAgent: mobile ? "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" : await browser.userAgent() });
await page.evaluateOnNewDocument(() => {
  window.__cls = 0; window.__shifts = [];
  new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) { window.__cls += e.value; window.__shifts.push([Math.round(e.startTime), +e.value.toFixed(4), e.sources ? e.sources.map((s) => s.node && s.node.className).join("|") : ""]); } })
    .observe({ type: "layout-shift", buffered: true });
});
const cdp = await page.createCDPSession();
const frames = [];
cdp.on("Page.screencastFrame", async (f) => {
  const i = frames.length, file = path.join(dir, "f" + String(i).padStart(5, "0") + ".jpg");
  fs.writeFileSync(file, Buffer.from(f.data, "base64"));
  frames.push([f.metadata.timestamp, file]);
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId });
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: width * dpr, maxHeight: height * dpr, everyNthFrame: 1 });
await page.goto(base + "index.html", { waitUntil: "load" });
await new Promise((r) => setTimeout(r, +hold));
const plan = await page.evaluate(() => {
  const pins = window.ScrollTrigger ? ScrollTrigger.getAll().filter((t) => t.vars.pin).map((t) => [t.start, t.end]) : [];
  return { max: document.documentElement.scrollHeight - innerHeight, pins };
});
await page.evaluate(async (speed, pinSpeed, pins) => {
  const max = () => document.documentElement.scrollHeight - innerHeight;
  let y = 0, prev = performance.now();
  await new Promise((done) => {
    function step(now) {
      const dt = Math.min(50, now - prev) / 1000; prev = now;
      const inPin = pins.some(([a, b]) => y >= a - 40 && y <= b + 40);
      y = Math.min(max(), y + dt * (inPin ? pinSpeed : speed));
      window.scrollTo({ top: y, behavior: "instant" });
      if (y >= max()) setTimeout(done, 1200); else requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
}, +speed, +pinSpeed, plan.pins);
await cdp.send("Page.stopScreencast");
const shifts = await page.evaluate(() => ({ cls: +window.__cls.toFixed(4), shifts: window.__shifts.slice(0, 20) }));
await browser.close();
// real time: each frame lasts until the next one was painted
const lines = [];
const gaps = [];
for (let i = 0; i < frames.length; i++) {
  const d = i + 1 < frames.length ? frames[i + 1][0] - frames[i][0] : 0.5;
  if (d > 0.1 && i > 0) gaps.push([i, +d.toFixed(3)]);
  lines.push("file '" + path.basename(frames[i][1]) + "'", "duration " + Math.max(0.001, d).toFixed(4));
}
lines.push("file '" + path.basename(frames[frames.length - 1][1]) + "'");
fs.writeFileSync(path.join(dir, "list.txt"), lines.join("\n") + "\n");
execFileSync(process.env.FFMPEG || "/opt/homebrew/bin/ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"),
  "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-movflags", "+faststart", out]);
const seconds = frames[frames.length - 1][0] - frames[0][0];
const report = { out, width, dpr, frames: frames.length, seconds: +seconds.toFixed(2), fps: +(frames.length / seconds).toFixed(1),
  gapsOver100ms: gaps.length, worstGaps: gaps.sort((a, b) => b[1] - a[1]).slice(0, 6), pins: plan.pins, ...shifts, errors };
fs.writeFileSync(out.replace(/\.mp4$/, ".json"), JSON.stringify(report, null, 1));
console.log(JSON.stringify(report));
