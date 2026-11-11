// Render brand/logo/src/*.svg to the PNGs listed in brand/logo/manifest.json (task RB2), plus two review
// sheets: brand/logo/in-use.png (the identity where it will be seen: browser tab, README header, avatar
// crops) and brand/logo/contact-sheet.png (every asset, the mark at true 16/32/64 px, and the in-use sheet).
// Usage: node brand/logo/render.mjs <node_modules dir holding @resvg/resvg-js>
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const brand = dirname(here);
const mods = process.argv[2] || join(dirname(brand), ".brandcache", "node_modules");
const { Resvg } = createRequire(join(mods, "noop.js"))("@resvg/resvg-js");

const render = (svgText, width) =>
  new Resvg(svgText, { fitTo: { mode: "width", value: width }, font: { loadSystemFonts: false } }).render().asPng();

const manifest = JSON.parse(readFileSync(join(here, "manifest.json"), "utf8"));
for (const [name, { src, width }] of Object.entries(manifest)) {
  writeFileSync(join(brand, name), render(readFileSync(join(brand, src), "utf8"), width));
  console.log("wrote brand/" + name, width + "px wide");
}

const inUse = readFileSync(join(here, "in-use.svg"), "utf8");
writeFileSync(join(here, "in-use.png"), render(inUse, 1320));
console.log("wrote brand/logo/in-use.png");

// Contact sheet: every PNG source scaled down, the mark at true 16/32/64 px (embedded as rendered PNGs,
// upscaled with nearest-neighbour so the real pixels can be inspected), then the in-use sheet.
const b64 = (buf) => "data:image/png;base64," + Buffer.from(buf).toString("base64");
const fav = readFileSync(join(brand, "favicon.svg"), "utf8");
// the dark 16 px drawing: the favicon with the dark theme's colours (ground, ink, accent, secondary)
const swap = { "#F2F4F1": "#121412", "#121412": "#F2F4F1", "#B82A16": "#FF7A59", "#55605A": "#B9C2BB" };
const favDark = fav.replace(/#[0-9A-F]{6}/g, (m) => swap[m] || m);
const mark = readFileSync(join(brand, "logo-mark.svg"), "utf8")
  .replace("role=\"img\">", "role=\"img\"><rect width=\"16\" height=\"16\" fill=\"#F2F4F1\"/>");
const markDark = readFileSync(join(brand, "logo-mark-reverse.svg"), "utf8")
  .replace("role=\"img\">", "role=\"img\"><rect width=\"16\" height=\"16\" fill=\"#121412\"/>");
const cells = [
  ["logo-light.png", 0, 0, 400], ["logo-dark.png", 420, 0, 400], ["avatar-512.png", 840, 0, 400],
  ["social-preview-1280x640.png", 0, 420, 800],
];
let body = cells.map(([n, x, y, w]) =>
  `<image x="${x}" y="${y}" width="${w}" height="${n.startsWith("social") ? w / 2 : w}" href="${b64(readFileSync(join(brand, n)))}"/>`).join("");
let x = 820;
for (const px of [16, 32, 64]) {
  const pair = px === 16 ? [fav, favDark] : [mark, markDark];
  for (const [i, s] of pair.entries()) {
    const size = px === 64 ? 192 : px * 6;
    body += `<image x="${x}" y="${420 + i * 210}" width="${size}" height="${size}" image-rendering="optimizeSpeed" href="${b64(render(s, px))}"/>`;
  }
  x += px === 16 ? 110 : 200;
}
body += `<image x="0" y="840" width="1320" height="460" href="${b64(readFileSync(join(here, "in-use.png")))}"/>`;
const sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="1340" height="1320" viewBox="-10 -10 1340 1320"><rect x="-10" y="-10" width="1340" height="1320" fill="#9AA39C"/>${body}</svg>`;
writeFileSync(join(here, "contact-sheet.png"), render(sheet, 1340));
console.log("wrote brand/logo/contact-sheet.png");
