// Frames of the hero replay at a fixed interval, for a frame strip and a check that nothing moves: every frame
// records the bounding boxes of the hero's blocks, and the run fails if any of them shifts while the replay plays.
// usage: NODE_PATH=... node heroframes.mjs <baseUrl> <outDir> [width=1440] [everyMs=500] [count=26]
import { createRequire } from "module";
import path from "path";
import fs from "fs";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [base, out, w = "1440", every = "500", count = "26"] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", args: ["--no-first-run", "--hide-scrollbars"],
});
const page = await browser.newPage();
const width = +w, mobile = width < 500;
await page.emulate({ viewport: { width, height: mobile ? 844 : 900, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile },
  userAgent: await browser.userAgent() });
const errors = [];
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(base + "index.html", { waitUntil: "networkidle0" });
if (mobile) await page.evaluate(() => document.querySelector("#replay").scrollIntoView({ block: "center", behavior: "instant" }));
await page.waitForFunction(() => document.querySelector("#replay pre.rp"), { timeout: 15000 });
const boxes = () => page.evaluate(() => [".hero h1", ".hero-panel", "#replay", ".hero-install", ".agents", "#gap"].map((s) => {
  const r = document.querySelector(s).getBoundingClientRect(); return [s, Math.round(r.top + scrollY), Math.round(r.height)];
}));
const first = JSON.stringify(await boxes());
let moved = 0;
const clipEl = "#replay";
for (let i = 0; i < +count; i++) {
  // a clip of the viewport where the panel is, never an element screenshot: that scrolls and resizes the page for
  // the shot, which takes the panel out of view and (correctly) sends the replay back to its still
  const r = await page.evaluate((s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, y: b.top + scrollY, width: b.width, height: b.height }; }, clipEl);
  await page.screenshot({ path: path.join(out, "f" + String(i).padStart(2, "0") + ".png"), clip: r });
  const now = JSON.stringify(await boxes());
  // more than 1 px on any box (a fractional scroll position rounds either way)
  const a = JSON.parse(first), b2 = JSON.parse(now);
  if (a.some((x, j) => Math.abs(x[1] - b2[j][1]) > 1 || Math.abs(x[2] - b2[j][2]) > 1)) { moved++; if (!globalThis.diff) globalThis.diff = now; }
  await new Promise((r) => setTimeout(r, +every));
}
// a contact sheet of every frame, four across, for one look at the whole pass
const files = fs.readdirSync(out).filter((f) => /^f\d+\.png$/.test(f)).sort();
const sheet = await browser.newPage();
await sheet.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
await sheet.setContent("<body style='margin:0;background:#F2F4F1;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:8px'>" +
  files.map((f, i) => "<figure style='margin:0;font:12px monospace'><img style='width:100%;display:block' src='data:image/png;base64," +
    fs.readFileSync(path.join(out, f)).toString("base64") + "'>" + (i * +every) + " ms</figure>").join("") + "</body>");
await sheet.screenshot({ path: path.join(out, "sheet.png"), fullPage: true });
console.log(JSON.stringify({ width, frames: +count, everyMs: +every, framesWithLayoutChange: moved, firstDiff: globalThis.diff ? JSON.parse(globalThis.diff) : null, errors, boxes: JSON.parse(first) }));
await browser.close();
