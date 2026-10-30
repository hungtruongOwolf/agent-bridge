/* Walks the whole replay by clicking the real screens, and fails (exit code 1) if anything is off.

     node demo-site/tools/smoke.mjs [--shots video-out/replay]     (serves demo-site itself; needs Chrome, uses puppeteer-core from tools/video)

   Checks: no console errors, no failed or off-site requests, the hold card, the approval page, the answer and its "Based on" list,
   the receipts ("25¢ of the 40¢ hold"), the first answer paid, "Not helpful" = deposit only, My memory, My helpers, a helper's profile,
   and a 390 px wide screen. */
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = resolve(HERE, "..");
const ROOT = resolve(SITE, "..");
const require = createRequire(resolve(ROOT, "tools/video/package.json"));
const puppeteer = require("puppeteer-core");
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const shotsArg = process.argv.indexOf("--shots");
const SHOTS = shotsArg > 0 ? resolve(process.argv[shotsArg + 1]) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };
// the same rule vercel.json states: a file if there is one, otherwise the console's page
const server = createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^([/\\])+/, "");
  let file = join(SITE, path);
  if (!file.startsWith(SITE) || !existsSync(file) || !extname(file)) file = join(SITE, "index.html");
  res.writeHead(200, { "Content-Type": TYPES[extname(file)] || "application/octet-stream" });
  res.end(readFileSync(file));
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const BASE = "http://127.0.0.1:" + server.address().port;

const failures = [];
const expect = (cond, msg) => { if (!cond) { failures.push(msg); console.error("FAIL:", msg); } else console.log("ok:", msg); };

function watch(page, label) {
  page.on("pageerror", (e) => expect(false, `${label}: page error ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") expect(false, `${label}: console error ${m.text()}`); });
  page.on("requestfailed", (r) => expect(false, `${label}: request failed ${r.url()}`));
  page.on("response", (r) => { if (r.status() >= 400 && !r.url().includes("/api/")) expect(false, `${label}: ${r.status()} ${r.url()}`); });
  page.on("request", (r) => { if (!r.url().startsWith(BASE) && !r.url().startsWith("data:") && !r.url().startsWith("blob:")) expect(false, `${label}: off-site request ${r.url()}`); });
}
async function find(page, sel, text, within = "body", timeout = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const h = await page.evaluateHandle((sel, text, within) => {
      const root = document.querySelector(within) || document.body;
      return [...root.querySelectorAll(sel)].find((e) => !text || e.textContent.includes(text)) || null;
    }, sel, text, within);
    if (h.asElement()) return h.asElement();
    await sleep(200);
  }
  throw new Error(`not found: ${sel} ${text || ""}`);
}
async function click(page, sel, text, within, after = 500) {
  const el = await find(page, sel, text, within);
  await el.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await sleep(100);
  await el.click();
  await sleep(after);
}
// a click on something inside a row: bring it to the middle of the screen first (the note bar sits over the bottom edge)
const tickBox = async (row, sel = "input[type=checkbox]") => { const e = await row.$(sel); await e.evaluate((x) => x.scrollIntoView({ block: "center" })); await sleep(120); await e.click(); };
const text = (page, sel = "body") => page.evaluate((sel) => (document.querySelector(sel) || document.body).innerText, sel);
const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: join(SHOTS, name + ".png") }); };

async function approve(browser, page, label) {
  const link = await find(page, "#convo .msg.system a.btn", "approval page", "body", 20000);
  const href = await link.evaluate((a) => a.href);
  expect(href.startsWith(BASE + "/approve.html"), `${label}: the approval link goes to this site's practice page`);
  const tab = await browser.newPage();
  watch(tab, label + " approval page");
  await tab.setViewport({ width: 900, height: 700 });
  await tab.goto(href, { waitUntil: "load" });
  const t = await text(tab);
  expect(/Practice server\. This imitates the PayPal sandbox\. No real money, no real PayPal account\./.test(t), `${label}: the approval page says it is a practice server`);
  expect(/Pay \$0\.40 USD/.test(t) || /Pay \$0\.\d\d USD/.test(t), `${label}: the approval page shows the hold`);
  await shot(tab, "approve-" + label);
  await click(tab, "button", "Approve the hold", "body", 600);
  await tab.close();
  await page.bringToFront();
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox", "--hide-scrollbars"] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 820 });
  watch(page, "main");
  await page.goto(BASE + "/", { waitUntil: "networkidle0" });
  let t = await text(page);
  expect(t.includes("Replay of a real run recorded on the practice PayPal server. Test money. Nothing here talks to PayPal or a model."), "the always-visible note is there");
  await shot(page, "01-office");

  const pick = await find(page, ".pick", "Account Brief");
  await (await pick.$(".btn.go2")).click();
  await page.waitForFunction(() => location.pathname.startsWith("/chats/"), { timeout: 10000 });
  await sleep(700);
  for (const name of ["Work", "Accounts"]) { const li = await find(page, "#sidebody li", name); await tickBox(li, ".twist"); await sleep(300); }
  { const li = await find(page, "#sidebody li", "Initech"); await tickBox(li); await sleep(700); }
  t = await text(page, "#sidebody");
  expect(/Initech/.test(t), "the shelf is ticked in the side panel");

  await page.waitForFunction(() => [...document.querySelectorAll("#replaybar button")].some((b) => b.textContent.includes("Fill in") && !b.hidden), { timeout: 5000 });
  await click(page, "#replaybar button", "Fill in the question", "body", 200);
  expect((await page.$eval("#draft", (d) => d.value)) === "Which accounts are at risk?", "the example question was filled in");
  await click(page, "#send", null, "body", 300);
  await find(page, "#convo .msg.system a.btn", "approval page", "body", 20000);
  t = await text(page, "#convo");
  expect(/Approve a hold of 40¢ on the payment page\. That is the most this answer can cost/.test(t), "the hold card says 40¢ is the most this answer can cost");
  await shot(page, "02-hold-card");

  await approve(browser, page, "hold1");
  await page.waitForFunction(() => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 1, { timeout: 30000 });
  await sleep(600);
  t = await text(page, "#convo");
  expect(/Initech/.test(t), "the first answer is about Initech");
  expect(/Based on|Based on these|These files/i.test(t) || (await page.$$("#convo .files, #convo .msg.helper .src, #convo .msg.helper details")).length > 0, "the answer lists the files it came from");
  await click(page, "#convo details summary", "How this answer was made", "body", 900);
  t = await text(page, "#convo");
  expect(/Nebius Token Factory/.test(t), "'How this answer was made' says what was sent to Nebius Token Factory");
  await shot(page, "03-answer");

  await click(page, "#coinbtn", null, "body", 900);
  await click(page, "#wallet summary", "What happened", "body", 500);
  t = await text(page, "#wallet");
  expect(/of the 40¢ hold/.test(t), "the receipt says how much of the 40¢ hold was priced");
  expect(/25¢/.test(t), "the receipt shows 25¢");
  await shot(page, "04-receipt");
  await click(page, "#wallet [data-close]", "Close", "body", 400);

  await page.waitForFunction(() => [...document.querySelectorAll("#replaybar button")].some((b) => b.textContent.includes("Fill in") && !b.hidden), { timeout: 5000 });
  await click(page, "#replaybar button", "Fill in the question", "body", 200);
  expect((await page.$eval("#draft", (d) => d.value)) === "And which one is the biggest?", "the second question was filled in");
  await click(page, "#send", null, "body", 300);
  await approve(browser, page, "hold2");
  await page.waitForFunction(() => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 2, { timeout: 30000 });
  await sleep(600);
  await click(page, "#coinbtn", null, "body", 900);
  t = await text(page, "#wallet");
  expect(/Paid/.test(t) && /author gets \d+¢ \(paid\)/.test(t), "asking again accepted the first answer: the author is paid");
  await shot(page, "05-accepted");
  await click(page, "#wallet [data-close]", "Close", "body", 400);

  await click(page, "#convo button.linkbtn", "Not helpful", "body", 1200);
  await click(page, "#coinbtn", null, "body", 900);
  const open = await page.$$("#wallet summary");
  for (const s of open.slice(0, 1)) await s.click();
  await sleep(500);
  t = await text(page, "#wallet");
  expect(/deposit only/.test(t), "'Not helpful' keeps the deposit only");
  await shot(page, "06-not-helpful");
  await click(page, "#wallet [data-close]", "Close", "body", 400);

  // reload in the middle of the story: it must show the same story
  await page.reload({ waitUntil: "networkidle0" });
  t = await text(page, "#convo");
  expect(/Which accounts are at risk\?/.test(t) && /And which one is the biggest\?/.test(t), "a reload keeps the whole conversation");

  await click(page, "button, a", "Meet Account Brief", "body", 900);
  await shot(page, "07-profile");
  await click(page, "#profile [data-close]", "Close", "body", 500);
  await click(page, "a[data-nav=memory]", null, "body", 1200);
  t = await text(page);
  expect(/139/.test(t), "My memory shows the 139 notes");
  await shot(page, "08-memory");
  await click(page, "a[data-nav=studio]", null, "body", 1200);
  t = await text(page);
  expect(/Account Brief/.test(t) && /Publish/.test(t), "My helpers shows the studio with the Publish tab");
  await click(page, "button, a", "Idea Sorter", "#view-studio", 1000).catch(() => {});
  await click(page, "button, a", "Publish", "#view-studio", 900).catch(() => {});
  await shot(page, "09-studio");

  // a click the replay does not cover must give a sentence, not a broken page
  await click(page, "button", "Create it", "#view-studio", 800).catch(() => {});
  t = await text(page);
  expect(!/Something went wrong|undefined|NaN/.test(t), "an uncovered click does not break the page");
  await shot(page, "10-uncovered");

  // start over works
  await click(page, "#replaybar button", "Start over", "body", 1200);
  t = await text(page);
  expect(/Account Brief/.test(t) && !/Which accounts are at risk\?/.test(await text(page, "#view-office")), "start over goes back to the empty office");

  // a narrow screen
  const phone = await browser.newPage();
  await phone.setViewport({ width: 390, height: 800, isMobile: true });
  watch(phone, "phone");
  await phone.goto(BASE + "/", { waitUntil: "networkidle0" });
  const wide = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide <= 40, `390 px wide: the page does not scroll sideways by much (${wide}px)`);
  const note = await phone.$eval("#replaybar", (e) => e.getBoundingClientRect().width);
  expect(note <= 391, "390 px wide: the note fits the screen");
  await shot(phone, "11-phone-office");
  const pk = await find(phone, ".pick", "Account Brief");
  await (await pk.$(".btn.go2")).click();
  await phone.waitForFunction(() => location.pathname.startsWith("/chats/"), { timeout: 10000 });
  await sleep(700);
  await shot(phone, "12-phone-chat");
} catch (e) {
  expect(false, "the walk-through stopped: " + e.message);
  try { const pg = (await browser.pages()).pop(); console.error("screen said:", (await text(pg, "#view-chat")).slice(0, 600).replace(/\s+/g, " "), "| state:", await pg.evaluate(() => localStorage.getItem("agent-bridge-replay"))); if (SHOTS) await shot(pg, "99-stopped"); } catch (_) { /* nothing more to say */ }
}
await browser.close();
server.close();
console.log(failures.length ? `\n${failures.length} problem(s)` : "\nall checks passed");
process.exit(failures.length ? 1 : 0);
