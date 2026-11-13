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
  ["shot-1-hero-1440.png", 1440, 900, 2, null],
  ["shot-2-tested-1440.png", 1440, 900, 2, "#tested .wrap"],
  ["shot-3-install-1440.png", 1440, 900, 2, "#install .wrap"],
  ["shot-4-phone-390.png", 390, 844, 3, null],
];
for (const [name, w, h, dpr, sel] of shots) {
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: dpr });
  await page.goto(base + "index.html", { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);
  if (sel) {
    const el = await page.$(sel);
    const box = await el.boundingBox();
    await page.screenshot({ path: path.join(out, name), clip: { x: 0, y: box.y - 56, width: w, height: box.height + 112 } });
  } else {
    await page.screenshot({ path: path.join(out, name) });
  }
  console.log("wrote", name);
  await page.close();
}
await browser.close();
