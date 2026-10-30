/* Renders tools/submission/pages/*.html to 1920 x 1280 PNGs (3:2).  node tools/submission/render.mjs [outDir]
   d* pages go to <outDir>/story, g* pages to <outDir>/gallery. */
import { mkdirSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { serve, launch } from "../video/render.mjs";
const HERE = fileURLToPath(new URL(".", import.meta.url)), ROOT = resolve(HERE, "../..");
const out = resolve(process.argv[2] || join(ROOT, "docs/submission/paypal"));
const { srv, port } = await serve();
const browser = await launch();
const page = await browser.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
page.on("requestfailed", (r) => console.error("request failed:", r.url()));
await page.setViewport({ width: 1280, height: 853, deviceScaleFactor: 1.5 });
for (const f of readdirSync(join(HERE, "pages")).filter((n) => n.endsWith(".html"))) {
  const name = f.replace(".html", "");
  const nebius = name.startsWith("nd") || name.startsWith("ng");
  const dir = join(nebius ? join(out, "../nebius") : out, name.startsWith("d") || name.startsWith("nd") ? "story" : "gallery");
  mkdirSync(dir, { recursive: true });
  await page.goto(`http://127.0.0.1:${port}/tools/submission/pages/${f}`, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: join(dir, name + ".png"), type: "png" });
  console.log(join(dir, name + ".png"));
}
await browser.close(); srv.close();
