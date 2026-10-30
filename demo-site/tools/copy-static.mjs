/* Copies the console's own front end into the replay site, so the replay always shows the real screens.

     node demo-site/tools/copy-static.mjs

   src/bridge/web/static  ->  demo-site/static   (unchanged)
   index.html             ->  demo-site/index.html  (the page token is a constant; the replay shim is loaded before the console's own scripts) */
import { copyFileSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "../../src/bridge/web/static");
const OUT = resolve(HERE, "..");

rmSync(resolve(OUT, "static"), { recursive: true, force: true });
const copy = (from, to) => {                                   // (fs.cpSync crashes node on this machine, so a plain walk)
  mkdirSync(to, { recursive: true });
  for (const name of readdirSync(from)) {
    const a = resolve(from, name), b = resolve(to, name);
    if (statSync(a).isDirectory()) copy(a, b); else copyFileSync(a, b);
  }
};
copy(SRC, resolve(OUT, "static"));
let html = readFileSync(resolve(SRC, "index.html"), "utf8");
if (!html.includes("__TOKEN__") || !html.includes('<script type="module" src="/static/js/main.js">')) throw new Error("the console's index.html changed; update sync.mjs");
html = html.replace("__TOKEN__", "replay").replace('<script type="module" src="/static/js/main.js">', '<script src="/shim.js"></script>\n<script type="module" src="/static/js/main.js">');
rmSync(resolve(OUT, "static/index.html"));   // the page is served as /index.html with its token filled in
writeFileSync(resolve(OUT, "index.html"), html);
console.log("synced static/ and index.html");
