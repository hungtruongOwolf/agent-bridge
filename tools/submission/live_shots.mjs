/* Screenshots of the hosted judge-mode site as a visitor sees it, 3:2 (1920 x 1280).  node tools/submission/live_shots.mjs <url> <outDir> */
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { launch } from "../video/render.mjs";
const [url, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1.3333 });
await page.goto(url, { waitUntil: "networkidle0", timeout: 120000 });
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: join(out, "g08-hosted-office.png"), type: "png" });
await page.goto(url.replace(/\/$/, "") + "/earnings", { waitUntil: "networkidle0", timeout: 60000 });
await new Promise((r) => setTimeout(r, 3000));
await page.screenshot({ path: join(out, "g09-hosted-earnings.png"), type: "png" });
await browser.close();
console.log("done");
