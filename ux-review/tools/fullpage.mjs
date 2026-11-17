// Full-page screenshots at 1440 / 834 / 390 (390 with device emulation: a headless window cannot be narrower
// than 500 px), after scrolling the whole page so every once-only entrance has run, plus the gate numbers:
// console errors, horizontal overflow, elements left faded, ScrollTriggers without an end.
// usage: NODE_PATH=... node fullpage.mjs <baseUrl> <outDir> [page=index.html]
import { createRequire } from "module";
import path from "path";
import fs from "fs";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [base, out, which = "index.html"] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", args: ["--no-first-run", "--hide-scrollbars"],
});
const widths = [[1440, 900, 1, false], [834, 1112, 1, true], [390, 844, 2, true]];
const report = {};
for (const [w, h, dpr, mobile] of widths) {
  const page = await browser.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(m.type() + ": " + m.text()); });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("requestfailed", (r) => errors.push("requestfailed: " + r.url()));
  await page.emulate({ viewport: { width: w, height: h, deviceScaleFactor: dpr, isMobile: mobile, hasTouch: mobile },
    userAgent: mobile ? "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" : (await browser.userAgent()) });
  await page.goto(base + which, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);
  await new Promise((r) => setTimeout(r, 3500));
  // walk the page so every once-only entrance fires, then back to the top
  await page.evaluate(async () => {
    const step = Math.round(innerHeight * 0.6);
    for (let y = 0; y < document.documentElement.scrollHeight; y += step) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 160)); }
    await new Promise((r) => setTimeout(r, 1600));
  });
  const gate = await page.evaluate(() => {
    const d = document.documentElement;
    const over = d.scrollWidth - d.clientWidth;
    d.scrollLeft = 50; const sl = d.scrollLeft; d.scrollLeft = 0;
    const faded = [...document.querySelectorAll("main *")].filter((el) => {
      const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && parseFloat(cs.opacity) < 0.9 && !el.closest("[aria-hidden=true]") && !el.closest(".film-frame");
    }).map((el) => el.tagName + "." + el.className).slice(0, 10);
    const st = window.ScrollTrigger ? ScrollTrigger.getAll().filter((t) => t.end === undefined || isNaN(t.end)).length : null;
    return { overflow: over, scrollLeft: sl, faded, stNoEnd: st, height: d.scrollHeight };
  });
  await page.evaluate(() => scrollTo(0, 0));
  await new Promise((r) => setTimeout(r, 2200));
  // the hero replay: shot on the still it ends on (heroframes.mjs records the motion)
  await page.evaluate(() => { const b = document.querySelector("#replay pre.rp .rp-btn"); if (b) b.click(); });
  await new Promise((r) => setTimeout(r, 300));
  const file = path.join(out, which.replace(/\W+/g, "-").replace(/-html$/, "") + "-" + w + ".png");
  await page.screenshot({ path: file, fullPage: true });
  // the same page in viewport-tall pieces, for looking at (a 15,000 px image is unreadable when scaled to fit)
  const piece = Math.round(h * 1.25);
  for (let i = 0, y = 0; y < gate.height; i++, y += piece) {
    await page.screenshot({ path: file.replace(/\.png$/, ".part" + String(i).padStart(2, "0") + ".png"),
      clip: { x: 0, y, width: w, height: Math.min(piece, gate.height - y) }, captureBeyondViewport: true });
  }
  report[w] = { ...gate, errors };
  console.log(w, JSON.stringify(report[w]));
  await page.close();
}
fs.writeFileSync(path.join(out, which.replace(/\W+/g, "-") + "-gate.json"), JSON.stringify(report, null, 2));
await browser.close();
