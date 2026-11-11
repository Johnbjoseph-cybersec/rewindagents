// Contact sheet of a VSL's key frames (task RB4b): every PNG in <keyframes dir>, in name order (b01a, b01b,
// b02a ...), two per row, each labelled by file name, so a reviewer can see the whole video at a glance before
// opening the full-size frames. Usage: node brand/vsl/sheet.mjs <keyframes dir> <out.png> [<node_modules>]
import { createRequire } from "node:module";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const [dir, out] = process.argv.slice(2, 4);
const mods = process.argv[4] || join(dirname(dirname(here)), ".brandcache", "node_modules");
const { Resvg } = createRequire(join(mods, "noop.js"))("@resvg/resvg-js");

const files = readdirSync(dir).filter((f) => f.endsWith(".png")).sort();
const size = (buf) => [buf.readUInt32BE(16), buf.readUInt32BE(20)];
const first = readFileSync(join(dir, files[0]));
const [w, h] = size(first);
const cols = w > h ? 2 : 4;
const tw = w > h ? 640 : 300, th = Math.round((tw * h) / w), gap = 16;
const rows = Math.ceil(files.length / cols);
const sw = cols * tw + (cols + 1) * gap, sh = rows * th + (rows + 1) * gap;
let body = `<rect width="${sw}" height="${sh}" fill="#838C86"/>`;
files.forEach((f, i) => {
  const x = gap + (i % cols) * (tw + gap), y = gap + Math.floor(i / cols) * (th + gap);
  const b64 = "data:image/png;base64," + readFileSync(join(dir, f)).toString("base64");
  body += `<image x="${x}" y="${y}" width="${tw}" height="${th}" href="${b64}"/>`;
});
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${sw}" height="${sh}" viewBox="0 0 ${sw} ${sh}">${body}</svg>`;
writeFileSync(out, new Resvg(svg, { fitTo: { mode: "width", value: sw } }).render().asPng());
console.log("wrote " + out + " (" + files.length + " frames)");
