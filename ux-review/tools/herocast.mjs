// The hero replay as the browser paints it, via the DevTools screencast (no screenshot calls, which on a mobile
// emulation resize the page for the shot and take the panel out of view). Writes frames every <everyMs> of the
// recording plus a contact sheet, cropped to the panel.
// usage: NODE_PATH=... node herocast.mjs <baseUrl> <outDir> [width=390] [everyMs=350] [seconds=11]
import { createRequire } from "module";
import path from "path";
import fs from "fs";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [base, out, w = "390", every = "350", secs = "11"] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
for (const f of fs.readdirSync(out)) if (/^(c\d+\.png|sheet\.png)$/.test(f)) fs.unlinkSync(path.join(out, f));
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", args: ["--no-first-run", "--hide-scrollbars"],
});
const page = await browser.newPage();
const width = +w, mobile = width < 500, height = mobile ? 844 : 900;
await page.emulate({ viewport: { width, height, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile }, userAgent: await browser.userAgent() });
await page.goto(base + "index.html", { waitUntil: "networkidle0" });
await page.evaluate(() => document.querySelector("#replay").scrollIntoView({ block: "center", behavior: "instant" }));
await page.waitForFunction(() => document.querySelector("#replay pre.rp"), { timeout: 15000 });
const box = await page.evaluate(() => { const r = document.querySelector("#replay").getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(Math.round); });
const cdp = await page.createCDPSession();
const frames = [];
cdp.on("Page.screencastFrame", async (f) => { frames.push([performance.now(), f.data]); await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); });
await cdp.send("Page.startScreencast", { format: "png", maxWidth: width, maxHeight: height });
await new Promise((r) => setTimeout(r, +secs * 1000));
await cdp.send("Page.stopScreencast");
const t0 = frames[0][0], picks = [];
for (let t = 0; t <= +secs * 1000; t += +every) {      // the last frame painted at or before each tick
  let best = frames[0]; for (const f of frames) if (f[0] - t0 <= t) best = f;
  picks.push([t, best[1]]);
}
const sheet = await browser.newPage();
await sheet.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
const cols = mobile ? 6 : 4;
await sheet.setContent("<body style='margin:0;background:#F2F4F1;display:grid;grid-template-columns:repeat(" + cols + ",1fr);gap:8px;padding:8px'>" +
  picks.map(([t, d]) => "<figure style='margin:0;font:12px monospace'><div style='overflow:hidden;aspect-ratio:" + box[2] + "/" + box[3] +
    ";position:relative'><img style='position:absolute;width:" + (width / box[2] * 100) + "%;left:" + (-box[0] / box[2] * 100) + "%;top:" + (-box[1] / box[3] * 100) +
    "%' src='data:image/png;base64," + d + "'></div>" + t + " ms</figure>").join("") + "</body>");
await sheet.screenshot({ path: path.join(out, "sheet.png"), fullPage: true });
picks.forEach(([t, d], i) => fs.writeFileSync(path.join(out, "c" + String(i).padStart(2, "0") + ".png"), Buffer.from(d, "base64")));
console.log(JSON.stringify({ width, painted: frames.length, picks: picks.length, panel: box }));
await browser.close();
