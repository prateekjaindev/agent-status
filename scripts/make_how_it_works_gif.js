// Capture docs/how-it-works.html frame by frame, then assemble with ffmpeg.
// Usage: NODE_PATH=<playwright/node_modules> node scripts/make_how_it_works_gif.js
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

(async () => {
  const root = path.resolve(__dirname, "..");
  const frames = path.join(root, "docs/.gif-frames");
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });

  const chrome = [process.env.CHROME, "/usr/bin/google-chrome-stable", "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].find((p) => p && fs.existsSync(p));
  const browser = await chromium.launch(chrome ? { executablePath: chrome } : {});
  const page = await browser.newPage({ viewport: { width: 900, height: 380 }, deviceScaleFactor: 1 });
  await page.goto("file://" + path.join(root, "docs/how-it-works.html"), { waitUntil: "load" });
  await page.waitForTimeout(300);
  await page.evaluate(() => document.getAnimations().forEach((a) => a.pause()));

  for (let i = 0; i < 80; i++) {           // 8 seconds at 10 fps
    await page.evaluate((t) => document.getAnimations().forEach((a) => { a.currentTime = t; }), i * 100);
    await page.screenshot({ path: path.join(frames, `f${String(i).padStart(3, "0")}.png`) });
  }
  await browser.close();
  const out = path.join(root, "docs/how-it-works.gif");
  execFileSync("ffmpeg", ["-y", "-framerate", "10", "-i", path.join(frames, "f%03d.png"),
    "-vf", "scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64:stats_mode=diff[p];[s1][p]paletteuse=dither=none",
    "-gifflags", "0", "-loop", "0", out], { stdio: "inherit" });
  fs.rmSync(frames, { recursive: true, force: true });
  console.log(`wrote ${out}`);
})();
