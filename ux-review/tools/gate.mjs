// The ux gate, measured in headless Chrome with its own profile.
// usage: node gate.mjs <baseUrl> <profileDir> > gate.json
// Per page and width: console errors, failed requests, horizontal overflow, overlapping text blocks, clipped
// boxes. Every link: local ones fetched (status) and anchors checked against ids; external ones listed for curl.
// The one-click select: click the hero install command, read the selection.
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [base, profile] = process.argv.slice(2);
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", userDataDir: profile, args: ["--no-first-run", "--hide-scrollbars"],
});
const pages = ["index.html", "pricing.html", "docs/"];
const out = { layout: {}, links: { local: [], anchors: [], external: [] }, select: {} };
const external = new Set();
for (const p of pages) {
  for (const w of [1440, 834, 390]) {
    const page = await browser.newPage();
    const errs = [], failed = [];
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
    page.on("pageerror", (e) => errs.push(String(e)));
    page.on("requestfailed", (r) => failed.push(r.url()));
    page.on("response", (r) => { if (r.status() >= 400) failed.push(r.status() + " " + r.url()); });
    await page.setViewport({ width: w, height: 900 });
    await page.goto(base + p, { waitUntil: "networkidle0" });
    await page.evaluate(() => document.fonts.ready);
    // load lazy images too, so a failing one would show
    await page.evaluate(async () => { for (const i of document.images) { i.loading = "eager"; } await new Promise((r) => setTimeout(r, 300)); });
    const m = await page.evaluate(() => {
      const de = document.documentElement, res = { overflowX: de.scrollWidth - de.clientWidth, overlaps: [], clipped: [], offRight: [] };
      for (const el of document.querySelectorAll("body *")) {
        const r = el.getBoundingClientRect();
        if (r.width && r.right > de.clientWidth + 0.5) res.offRight.push(el.tagName + "." + el.className);
        const cs = getComputedStyle(el);
        if (["hidden", "clip"].includes(cs.overflowX) || ["hidden", "clip"].includes(cs.overflowY))
          if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) res.clipped.push(el.tagName + "." + el.className);
      }
      const leaves = [...document.querySelectorAll("h1,h2,h3,p,li,a,pre,img,figcaption,summary,svg.ruler")]
        .filter((el) => { if (el.tagName !== "SUMMARY" && el.closest("details:not([open])")) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
      for (let i = 0; i < leaves.length; i++) for (let j = i + 1; j < leaves.length; j++) {
        const a = leaves[i], b = leaves[j];
        if (a.contains(b) || b.contains(a)) continue;
        const r1 = a.getBoundingClientRect(), r2 = b.getBoundingClientRect();
        const ox = Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left), oy = Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top);
        if (ox > 1 && oy > 1) res.overlaps.push(a.tagName + "." + a.className + " x " + b.tagName + "." + b.className);
      }
      return res;
    });
    m.consoleErrors = errs; m.failedRequests = failed;
    out.layout[p + "@" + w] = m;
    if (w === 1440) {
      const links = await page.evaluate(() => [...document.querySelectorAll("a[href], link[href], img[src]")].map((a) => [a.getAttribute("href") || a.getAttribute("src"), (a.href || a.src)]));
      for (const [raw, abs] of links) {
        if (/^https?:/.test(raw)) { if (!abs.startsWith(base)) external.add(abs); continue; }
        if (raw.startsWith("#")) {
          const ok = await page.evaluate((id) => !!document.getElementById(id), raw.slice(1));
          out.links.anchors.push([p, raw, ok]); continue;
        }
        const url = new URL(abs); const hash = url.hash; url.hash = "";
        const r = await fetch(url.href);
        let ok = r.ok;
        if (ok && hash) { const t = await r.text(); ok = t.includes(' id="' + hash.slice(1) + '"'); }
        out.links.local.push([p, raw, r.status, ok]);
      }
    }
    if (p === "index.html") {
      const sel = await page.evaluate(() => {
        const el = document.querySelector(".hero-install .sel");
        el.scrollIntoView({ block: "center" });
        const r = el.getClientRects()[0];      // the first line box of the command
        return { x: r.left + 20, y: r.top + r.height / 2 };
      });
      await page.mouse.click(sel.x, sel.y);
      out.select[w] = await page.evaluate(() => getSelection().toString());
    }
    await page.close();
  }
}
out.links.external = [...external].sort();
console.log(JSON.stringify(out, null, 1));
await browser.close();
