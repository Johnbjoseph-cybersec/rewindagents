// Render the share cards that `python3 brand/site/build.py cards DIR` writes, at their exact pixel size.
// usage: node cards.mjs <cardsDir> <outDir> <chromeProfileDir>
// Needs puppeteer-core (NODE_PATH or a local install) and Google Chrome. Writes og-1200x630.png,
// linkedin-1200x627.png and card-1080x1350.png, and fails if any element spills past the card.
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [dir, out, profile] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", userDataDir: profile, args: ["--no-first-run", "--hide-scrollbars", "--allow-file-access-from-files"],
});
const jobs = [["og.html", 1200, 630, "og-1200x630.png"], ["linkedin.html", 1200, 627, "linkedin-1200x627.png"],
              ["portrait.html", 1080, 1350, "card-1080x1350.png"]];
let bad = 0;
for (const [file, w, h, name] of jobs) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  await page.goto("file://" + path.resolve(dir, file), { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);
  const spill = await page.evaluate((w, h) => {
    const out = [];
    for (const el of document.querySelectorAll(".card *")) {
      const r = el.getBoundingClientRect();
      if (r.width && (r.right > w + 0.5 || r.bottom > h + 0.5 || r.left < -0.5)) out.push(el.tagName + "." + el.className);
      if (el.matches("pre.term") && el.scrollWidth > el.clientWidth + 1) out.push("wide terminal row in " + el.className);
    }
    return out;
  }, w, h);
  if (spill.length) { bad++; console.log(name, "SPILL", spill.slice(0, 5)); }
  await page.screenshot({ path: path.join(out, name), clip: { x: 0, y: 0, width: w, height: h } });
  console.log("wrote", name, w + "x" + h);
  await page.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
