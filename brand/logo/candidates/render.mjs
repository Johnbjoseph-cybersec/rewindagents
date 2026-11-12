// Render brand/logo/candidates/sheet.svg to sheet.png (task RB2d review material), plus each candidate's 16 px
// drawing at true size and 8x nearest-neighbour in tiles.png so the real pixels can be inspected.
// Usage: node brand/logo/candidates/render.mjs <node_modules dir holding @resvg/resvg-js>
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(dirname(dirname(here)));
const mods = process.argv[2] || join(root, ".brandcache", "node_modules");
const { Resvg } = createRequire(join(mods, "noop.js"))("@resvg/resvg-js");
const render = (svgText, width) =>
  new Resvg(svgText, { fitTo: { mode: "width", value: width }, font: { loadSystemFonts: false } }).render().asPng();

writeFileSync(join(here, "sheet.png"), render(readFileSync(join(here, "sheet.svg"), "utf8"), 1320));
console.log("wrote brand/logo/candidates/sheet.png");

const b64 = (buf) => "data:image/png;base64," + Buffer.from(buf).toString("base64");
let body = "";
["A", "B", "C"].forEach((k, i) => {
  const fav = readFileSync(join(here, `${k}-favicon.svg`), "utf8");
  const mark = readFileSync(join(here, `${k}-mark.svg`), "utf8")
    .replace('role="img">', 'role="img"><rect width="16" height="16" fill="#F2F4F1"/>');
  const y = i * 150;
  body += `<image x="0" y="${y}" width="16" height="16" href="${b64(render(fav, 16))}"/>`;
  body += `<image x="30" y="${y}" width="128" height="128" image-rendering="optimizeSpeed" href="${b64(render(fav, 16))}"/>`;
  body += `<image x="180" y="${y}" width="128" height="128" image-rendering="optimizeSpeed" href="${b64(render(mark, 32))}"/>`;
});
const tiles = `<svg xmlns="http://www.w3.org/2000/svg" width="330" height="440" viewBox="-10 -10 330 440"><rect x="-10" y="-10" width="330" height="440" fill="#9AA39C"/>${body}</svg>`;
writeFileSync(join(here, "tiles.png"), render(tiles, 660));
console.log("wrote brand/logo/candidates/tiles.png");
