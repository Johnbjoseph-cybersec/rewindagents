// Render brand/demo/frames/*.svg to PNG (task RB2b), copy the key frames at full size to
// brand/demo/keyframes/ and draw a contact sheet of them (brand/demo/contact-sheet.png), so the demo
// can be looked at, frame by frame, before anyone grades it.
// Usage: node brand/demo/render.mjs [<node_modules dir holding @resvg/resvg-js>]
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frames = join(here, "frames");
const mods = process.argv[2] || join(dirname(dirname(here)), ".brandcache", "node_modules");
const { Resvg } = createRequire(join(mods, "noop.js"))("@resvg/resvg-js");

const render = (svgText, width) =>
  new Resvg(svgText, { fitTo: { mode: "width", value: width }, font: { loadSystemFonts: false } }).render().asPng();

const plan = JSON.parse(readFileSync(join(frames, "frames.json"), "utf8"));
const pngs = [];
for (const row of plan.frames) {
  const png = render(readFileSync(join(frames, row.svg), "utf8"), plan.width);
  writeFileSync(join(frames, row.png), png);
  pngs.push(png);
}
console.log("rendered " + pngs.length + " frames at " + plan.width + "x" + plan.height);

// key frames at full size: the opening prompt, then the end of every beat
const keys = join(here, "keyframes");
rmSync(keys, { recursive: true, force: true });
mkdirSync(keys);
plan.keyframes.forEach((k, i) => writeFileSync(join(keys, `k${i}-frame${String(k).padStart(4, "0")}.png`), pngs[k]));
console.log("wrote " + plan.keyframes.length + " key frames to brand/demo/keyframes/");

// contact sheet: the key frames, two columns, on the Leader ground
const b64 = (buf) => "data:image/png;base64," + Buffer.from(buf).toString("base64");
const tw = 580, th = Math.round((tw * plan.height) / plan.width), gap = 16;
const cols = 2, rows = Math.ceil(plan.keyframes.length / cols);
const sw = cols * tw + (cols + 1) * gap, sh = rows * th + (rows + 1) * gap;
let body = `<rect width="${sw}" height="${sh}" fill="#838C86"/>`;
plan.keyframes.forEach((k, i) => {
  const x = gap + (i % cols) * (tw + gap), y = gap + Math.floor(i / cols) * (th + gap);
  body += `<image x="${x}" y="${y}" width="${tw}" height="${th}" href="${b64(pngs[k])}"/>`;
});
const sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="${sw}" height="${sh}" viewBox="0 0 ${sw} ${sh}">${body}</svg>`;
writeFileSync(join(here, "contact-sheet.png"), render(sheet, sw));
console.log("wrote brand/demo/contact-sheet.png (" + plan.keyframes.length + " key frames)");
