// Launch screenshots of the real built site, at 2x (3x for the phone).
// usage: node shots.mjs <baseUrl> <outDir> <chromeProfileDir>
import { createRequire } from "module";
import path from "path";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [base, out, profile] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", userDataDir: profile, args: ["--no-first-run", "--hide-scrollbars"],
});
const shots = [
  ["shot-1-hero-1440.png", 1440, 900, 2, null, ".hero-install"],
  ["shot-2-fork-1440.png", 1440, 900, 2, "#fork .wrap"],
  ["shot-3-tested-1440.png", 1440, 900, 2, "#tested .wrap"],
  ["shot-4-install-1440.png", 1440, 900, 2, "#install .wrap"],
  ["shot-5-phone-390.png", 390, 844, 3, null, ".hero-install"],
];
for (const [name, w, h, dpr, sel, until] of shots) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: dpr });
  // the still a reader sees with motion settled: site.js honours reduced motion and shows the page as built
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  await page.goto(base + "index.html", { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);
  let clip = { x: 0, y: 0, width: w, height: h };
  if (until) {   // a first-screen shot ends in white space under a whole block, never through a line of text
    const box = await (await page.$(until)).boundingBox();
    clip = { x: 0, y: 0, width: w, height: Math.round(box.y + box.height + 40) };
  }
  if (sel) {
    const box = await (await page.$(sel)).boundingBox();
    clip = { x: 0, y: Math.round(box.y - 56), width: w, height: Math.round(box.height + 112) };
  }
  const shot = await page.screenshot({ clip, captureBeyondViewport: true, encoding: "base64" });
  // the credit band under every shot (John, 2026-11-13: "made by John B Joseph" on every launch asset), set in
  // the site's own type and colours from the built page, never typed into the picture
  const band = await page.evaluate(() => ({ credit: document.querySelector(".foot .credit").textContent,
    host: new URL(document.querySelector('link[rel="canonical"]').href).host }));
  const card = await browser.newPage();
  await card.setViewport({ width: w, height: clip.height + 56, deviceScaleFactor: dpr });
  // a page of its own (the site's CSP rightly refuses a data: image), with the site's stylesheet for the type
  await card.setContent('<!doctype html><html><head><base href="' + base + '"><link rel="stylesheet" href="site.css"></head><body></body></html>',
    { waitUntil: "networkidle0" });
  await card.evaluate((src, band, w, hh) => {
    document.body.style.cssText = "margin:0;background:var(--leader)";
    const img = new Image(); img.style.cssText = "display:block;width:" + w + "px;height:" + hh + "px";
    const b = document.createElement("div");
    b.style.cssText = "height:56px;box-sizing:border-box;padding:0 " + (w > 600 ? 152 : 16) + "px;display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--rule);font:14px/1 var(--mono);color:var(--tape)";
    const l = document.createElement("b"); l.textContent = band.host; l.style.color = "var(--reel)";
    const r = document.createElement("span"); r.textContent = band.credit;
    b.append(l, r); document.body.append(img, b);
    const done = new Promise((ok, no) => { img.onload = ok; img.onerror = no; });
    img.src = src;
    return done.then(() => document.fonts.ready);
  }, "data:image/png;base64," + shot, band, w, clip.height);
  await card.screenshot({ path: path.join(out, name) });
  await card.close();
  console.log("wrote", name);
  await page.close();
}
await browser.close();
