/* Renders a thumbnail page as a still image.  node thumb.mjs anim/thumb-nebius.html out.png [16x9|3x2]
   16x9 = 1920 x 1080 (YouTube).  3x2 = 1920 x 1280 (Devpost). */
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { serve, launch } from "./render.mjs";
const HERE = fileURLToPath(new URL(".", import.meta.url)), ROOT = resolve(HERE, "../..");
const [pageFile, out, shape = "16x9"] = process.argv.slice(2);
const tall = shape === "3x2";
const { srv, port } = await serve();
const browser = await launch();
const page = await browser.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.setViewport({ width: 1280, height: tall ? 853 : 720, deviceScaleFactor: 1.5 });
const rel = resolve(HERE, pageFile).slice(ROOT.length).split("\\").join("/");
await page.goto(`http://127.0.0.1:${port}${rel}?d=10${tall ? "&r=32" : ""}`, { waitUntil: "networkidle0" });
await page.evaluate(() => document.fonts.ready);
await page.waitForFunction("window.ready === true");
await page.evaluate(() => window.seek(0));
await page.screenshot({ path: out, type: "png" });
console.log(out);
await browser.close(); srv.close();
