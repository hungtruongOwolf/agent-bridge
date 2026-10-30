/* Records a real session of the console: every /api/* request and its JSON reply, in order, into demo-site/fixtures/trace.json.
   The replay (shim.js) answers from this file, so the site needs no server.

     node demo-site/tools/capture.mjs [http://127.0.0.1:8795]

   Start the console first with the practice PayPal server and a fresh state (no earlier chats or receipts), for example:
     bridge serve --state .bridge-replay --vault examples/vault-library.json --payments paypal-mock --port 8795
   It drives the same screens a person would click: new chat with Account Brief, tick Work > Accounts > Initech, ask, approve the hold
   on the practice PayPal page, read the answer and receipts, ask again (which accepts the first answer), say "Not helpful", then look at
   My memory, My helpers (the studio) and the helper's profile. */
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const require = createRequire(resolve(ROOT, "tools/video/package.json"));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.argv[2] || "http://127.0.0.1:8795";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const trace = [];
let n = 0;

function watch(page) {
  page.on("response", async (res) => {
    const u = new URL(res.url());
    if (!u.pathname.startsWith("/api/") || u.origin !== BASE) return;
    const req = res.request();
    let json = null;
    try { json = await res.json(); } catch (_) { /* not JSON */ }
    let body = null;
    try { body = req.postData() ? JSON.parse(req.postData()) : null; } catch (_) { /* not JSON */ }
    trace.push({ n: n++, method: req.method(), path: u.pathname, query: Object.fromEntries(u.searchParams), body, status: res.status(), json });
  });
}

const mark = (label) => { trace.push({ n: n++, mark: label }); console.log("mark", label); };

/** First element matching `sel` whose own text contains `text`, inside `within` (a selector). */
async function find(page, sel, text, within = "body", timeout = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const h = await page.evaluateHandle((sel, text, within) => {
      const root = document.querySelector(within) || document.body;
      return [...root.querySelectorAll(sel)].find((e) => !text || e.textContent.includes(text)) || null;
    }, sel, text, within);
    const el = h.asElement();
    if (el) return el;
    await sleep(250);
  }
  throw new Error(`not found: ${sel} ${text || ""}`);
}
async function click(page, sel, text, within, after = 700) {
  const el = await find(page, sel, text, within);
  await el.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await sleep(150);
  await el.click();
  await sleep(after);
}
const waitFor = (page, fn, timeout = 120000) => page.waitForFunction(fn, { timeout, polling: 300 });

async function ask(page, text) {
  await click(page, "#draft", null, "body", 200);
  await page.keyboard.type(text, { delay: 15 });
  await click(page, "#send", null, "body", 300);
}

async function approve(browser, page) {
  const link = await find(page, "#convo .msg.system a.btn", "approval page");
  const href = await link.evaluate((a) => a.href);
  mark("approve_url:" + href);
  const tab = await browser.newPage();
  watch(tab);
  await tab.goto(href, { waitUntil: "networkidle0" });
  await sleep(800);
  await tab.screenshot({ path: resolve(ROOT, "video-out/replay-approve-page.png") });
  await click(tab, "button, a, input[type=submit]", "Approve the hold", "body", 1200);
  await sleep(900);
  await tab.close().catch(() => {});
  await page.bringToFront();
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox", "--hide-scrollbars"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
watch(page);
page.on("pageerror", (e) => console.error("page error:", e.message));

mark("office");
await page.goto(BASE + "/", { waitUntil: "networkidle0" });
await sleep(800);

mark("new-chat");
await click(page, "a.stall.newstall", null, "body", 900).catch(() => {});
const pick = await find(page, ".pick", "Account Brief");
await (await pick.$(".btn.go2")).click();
await waitFor(page, () => location.pathname.startsWith("/chats/"));
await sleep(900);
mark("tick");
await click(page, "#sidebody li .twist", "", "#sidebody", 0).catch(() => {});
for (const name of ["Work", "Accounts"]) {
  const li = await find(page, "#sidebody li", name);
  await (await li.$(".twist")).click(); await sleep(500);
}
{ const li = await find(page, "#sidebody li", "Initech"); await (await li.$("input[type=checkbox]")).click(); await sleep(900); }

mark("ask1");
await ask(page, "Which accounts are at risk?");
await find(page, "#convo .msg.system a.btn", "approval page", "body", 90000);
await sleep(700);
mark("card1");
await approve(browser, page);
await waitFor(page, () => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 1);
await sleep(1500);
mark("answer1");
// the answer's own details
const how = await find(page, "#convo details summary", "How this answer was made");
await how.click(); await sleep(1200);
mark("how1");
await click(page, "#coinbtn", null, "body", 1500);
mark("wallet1");
await find(page, "#wallet summary, #wallet .receipt summary, #wallet details summary", "What happened").then((e) => e.click()).catch(() => {});
await sleep(900);
await click(page, "#wallet [data-close]", "Close", "body", 900);

mark("ask2");
await ask(page, "And which one is the biggest?");
await find(page, "#convo .msg.system a.btn", "approval page", "body", 90000);
await sleep(500);
mark("card2");
await approve(browser, page);
await waitFor(page, () => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 2);
await sleep(1500);
mark("answer2");
{ const all = await page.$$("#convo details summary"); if (all.length) { await all[all.length - 1].click(); await sleep(1200); } }
mark("how2");
await click(page, "#coinbtn", null, "body", 1500);
mark("wallet2");
await click(page, "#wallet [data-close]", "Close", "body", 900);

mark("not-helpful");
await click(page, "#convo button.linkbtn", "Not helpful", "body", 1800);
mark("after-not-helpful");
await click(page, "#coinbtn", null, "body", 1500);
mark("wallet3");
const wh = await find(page, "#wallet summary", "What happened").catch(() => null);
if (wh) { await wh.click(); await sleep(700); }
await click(page, "#wallet [data-close]", "Close", "body", 900);

mark("profile");
await click(page, "button, a", "Meet Account Brief", "body", 1800);
await sleep(800);

// pages that are only read: the memory map, the studio and every helper's profile. Fetched the way the pages fetch them.
mark("extras");
const get = (path) => page.evaluate(async (path) => { const r = await fetch(path); return { status: r.status, json: await r.json().catch(() => null) }; }, path);
const grab = async (path) => {
  const r = await get(path);
  const u = new URL(path, BASE);
  trace.push({ n: n++, method: "GET", path: u.pathname, query: Object.fromEntries(u.searchParams), body: null, status: r.status, json: r.json, extra: true });
  return r.json;
};
await grab("/api/memory/tree");
await grab("/api/memory/trash");
await grab("/api/memory?offset=0&limit=100");
await grab("/api/memory?offset=100&limit=100");
const studio = await grab("/api/studio");
const ids = (studio.helpers || studio.items || studio.list || []).map((h) => h.id);
console.log("studio helpers:", JSON.stringify(ids));
for (const id of ids) await grab("/api/studio/helper?id=" + encodeURIComponent(id));
const state = await grab("/api/state");
for (const m of state.market) await grab("/api/agent?key=" + encodeURIComponent(m.key));
await page.goto(BASE + "/memory", { waitUntil: "networkidle0" }); await sleep(800);
await page.goto(BASE + "/helpers", { waitUntil: "networkidle0" }); await sleep(800);

mkdirSync(resolve(HERE, "../fixtures"), { recursive: true });
writeFileSync(resolve(HERE, "../fixtures/trace.json"), JSON.stringify(trace, null, 1));
console.log("trace entries:", trace.length);
await browser.close();
