/* Renders an animation page to a video, one exact frame at a time.

     node render.mjs anim/n01.html ../../video-out/n01.mp4 --duration 14 [--fps 30] [--still 5.5 out.png]

   The page must define window.seek(t) (t in seconds) that draws that moment and nothing else: no timers, no real clock.
   It reads its total length from the query string (?d=14), so the same scene can be re-rendered to match the voice exactly.
   The page is shown at 1280 x 720 CSS pixels and captured at 1920 x 1080. */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const ROOT = resolve(HERE, "../..");  // the repository root, so pages can use the console's fonts and pixel art
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };

export function serve(root = ROOT) {
  const srv = createServer(async (req, res) => {
    try {
      const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^([/\\])+/, "");
      const file = join(root, path);
      if (!file.startsWith(root)) throw new Error("outside");
      const body = await readFile(file);
      res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
      res.end(body);
    } catch { res.writeHead(404); res.end(); }
  });
  return new Promise((ok) => srv.listen(0, "127.0.0.1", () => ok({ srv, port: srv.address().port })));
}

export async function launch() {
  return puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1"] });
}

function arg(name, def) {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? process.argv[i + 1] : def;
}

async function main() {
  const [page_, out] = process.argv.slice(2).filter((a) => !a.startsWith("--") && isNaN(a));
  const dur = parseFloat(arg("duration", "10")), fps = parseInt(arg("fps", "30"), 10), still = arg("still", null);
  const { srv, port } = await serve();
  const browser = await launch();
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.error("page error:", e.message));
  page.on("requestfailed", (r) => console.error("request failed:", r.url()));
  await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1.5 });
  const [pageFile, pageQuery = ""] = page_.split("?");
  const rel = resolve(HERE, pageFile).slice(ROOT.length).replace(/\\/g, "/");
  await page.goto(`http://127.0.0.1:${port}${rel}?d=${dur}&${pageQuery}`, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction("window.ready === true || typeof window.seek === 'function'");
  if (still !== null) {
    await page.evaluate((t) => window.seek(t), parseFloat(still));
    await page.screenshot({ path: out, type: "png", omitBackground: process.argv.includes("--transparent") });
    console.log("still", still, "->", out);
  } else {
    const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium", "-r", String(fps), out], { stdio: ["pipe", "inherit", "inherit"] });
    const n = Math.round(dur * fps);
    for (let i = 0; i < n; i++) {
      await page.evaluate((t) => window.seek(t), i / fps);
      const buf = await page.screenshot({ type: "jpeg", quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
      if (i % 60 === 0) process.stdout.write(`\r${out}: ${i}/${n}`);
    }
    ff.stdin.end();
    await new Promise((r) => ff.on("close", r));
    console.log(`\r${out}: ${n} frames, ${dur}s`);
  }
  await browser.close();
  srv.close();
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((e) => { console.error(e); process.exit(1); });
