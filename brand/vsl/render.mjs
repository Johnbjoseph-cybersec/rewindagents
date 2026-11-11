// Render one VSL's unique frames (brand/vsl/frames/<name>/u*.svg, listed in frames.json) to PNG beside them
// (task RB4b). brand/vsl/render.py writes the SVGs and then calls this.
// Usage: node brand/vsl/render.mjs <frames dir> [<node_modules dir holding @resvg/resvg-js>]
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dir = process.argv[2];
const mods = process.argv[3] || join(dirname(dirname(here)), ".brandcache", "node_modules");
const { Resvg } = createRequire(join(mods, "noop.js"))("@resvg/resvg-js");

const plan = JSON.parse(readFileSync(join(dir, "frames.json"), "utf8"));
for (const svg of plan.svgs) {
  const png = new Resvg(readFileSync(join(dir, svg), "utf8"), {
    fitTo: { mode: "width", value: plan.width },
    font: { loadSystemFonts: false },
  }).render().asPng();
  writeFileSync(join(dir, svg.replace(/\.svg$/, ".png")), png);
}
console.log("rendered " + plan.svgs.length + " frames at " + plan.width + "x" + plan.height);
