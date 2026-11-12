// Render the RB2f review sheet: sheet.svg -> sheet.png at 1:1, tiles.svg -> tiles.png at 2x (whole pixels).
// Usage: node brand/logo/round2-concepts/render.mjs [<node_modules dir holding @resvg/resvg-js>]
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(dirname(dirname(here)));
const mods = process.argv[2] || join(root, ".brandcache", "node_modules");
const { Resvg } = createRequire(join(mods, "noop.js"))("@resvg/resvg-js");
const render = (svgText, width) =>
  new Resvg(svgText, { fitTo: { mode: "width", value: width }, font: { loadSystemFonts: false } })
    .render().asPng();

for (const [name, scale] of [["sheet", 1], ["tiles", 2]]) {
  const svg = readFileSync(join(here, `${name}.svg`), "utf8");
  const w = Number(/width="([\d.]+)"/.exec(svg.slice(svg.indexOf("<svg")))[1]);
  writeFileSync(join(here, `${name}.png`), render(svg, w * scale));
  console.log(`wrote brand/logo/round2-concepts/${name}.png`);
}
