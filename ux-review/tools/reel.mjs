// Screenshot reel.html (ux-review/tools/reel.py) frame by frame, then encode MP4 and GIF with ffmpeg.
// usage: node reel.mjs <reelDir> <outDir> <chromeProfileDir> [fps]
import { createRequire } from "module";
import fs from "fs";
import path from "path";
import { execFileSync } from "child_process";
const require = createRequire(import.meta.url);
const puppeteer = require(process.env.PUPPETEER || "puppeteer-core");
const [dir, out, profile, fpsArg] = process.argv.slice(2);
const fps = Number(fpsArg || 25);
const frames = path.join(dir, "frames");
fs.rmSync(frames, { recursive: true, force: true }); fs.mkdirSync(frames, { recursive: true }); fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "new", userDataDir: profile, args: ["--no-first-run", "--hide-scrollbars", "--allow-file-access-from-files"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
await page.goto("file://" + path.resolve(dir, "reel.html"), { waitUntil: "networkidle0" });
await page.evaluate(() => document.fonts.ready);
const dur = await page.evaluate(() => window.DURATION);
const n = Math.ceil(dur * fps);
for (let i = 0; i < n; i++) {
  await page.evaluate((t) => window.show(t), i / fps);
  await page.screenshot({ path: path.join(frames, String(i).padStart(4, "0") + ".png") });
}
await browser.close();
const mp4 = path.join(out, "rewind-in-action-1280x720.mp4"), gif = path.join(out, "rewind-in-action-800.gif");
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", path.join(frames, "%04d.png"),
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", mp4]);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", path.join(frames, "%04d.png"),
  "-vf", "fps=12,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=none", gif]);
console.log("frames", n, "seconds", dur.toFixed(1), "->", mp4, gif);
