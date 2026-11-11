// Render brand/logo/src/*.svg to the PNGs listed in brand/logo/manifest.json (task RB2), plus a contact
// sheet (brand/logo/contact-sheet.png) for looking at every asset, including the mark at 16 and 32 px.
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

// Contact sheet: every PNG source scaled down, then the mark at true 16/32/64 px (embedded as rendered PNGs,
// upscaled 6x with nearest-neighbour so the real pixels can be inspected).
const b64 = (buf) => "data:image/png;base64," + Buffer.from(buf).toString("base64");
const mark = readFileSync(join(brand, "favicon.svg"), "utf8");
const rev = readFileSync(join(brand, "logo-mark-reverse.svg"), "utf8")
  .replace("role=\"img\">", "role=\"img\"><rect width=\"16\" height=\"16\" fill=\"#121412\"/>");
const cells = [
  ["logo-light.png", 0, 0, 400], ["logo-dark.png", 420, 0, 400], ["avatar-512.png", 840, 0, 400],
  ["social-preview-1280x640.png", 0, 420, 800],
];
let body = cells.map(([n, x, y, w]) =>
  `<image x="${x}" y="${y}" width="${w}" height="${n.startsWith("social") ? w / 2 : w}" href="${b64(readFileSync(join(brand, n)))}"/>`).join("");
let x = 820;
for (const px of [16, 32, 64]) {
  for (const [i, s] of [mark, rev].entries()) {
    const size = px === 64 ? 192 : px * 6;
    body += `<image x="${x}" y="${420 + i * 210}" width="${size}" height="${size}" style="image-rendering:pixelated" href="${b64(render(s, px))}"/>`;
  }
  x += px === 16 ? 110 : 200;
}
const sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="1340" height="840" viewBox="-10 -10 1340 840"><rect x="-10" y="-10" width="1340" height="840" fill="#9AA39C"/>${body}</svg>`;
writeFileSync(join(here, "contact-sheet.png"), render(sheet, 1340));
console.log("wrote brand/logo/contact-sheet.png");
