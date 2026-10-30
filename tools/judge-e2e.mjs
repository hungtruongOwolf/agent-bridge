/* End-to-end check of judge mode with headless Chrome: two independent visitors, each hires Account Brief, approves the hold on /practice,
   reads the answer and the receipt ("25¢ of the 40¢ hold"), keeps going (accept), then says "Not helpful".
   usage: node tools/judge-e2e.mjs http://127.0.0.1:9101      (start `bridge serve --judge-mode --port 9101` first) */
import { createRequire } from "node:module";
const require = createRequire(new URL("./video/", import.meta.url));
const puppeteer = require("puppeteer-core");
const BASE = process.argv[2] || "http://127.0.0.1:9101";
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) failed++; };

async function waitFor(page, fn, timeout = 60000, ...a) { await page.waitForFunction(fn, { timeout }, ...a); }
async function clickIn(page, sel, text, inner) {
  const h = await page.evaluateHandle((sel, text, inner) => {
    const el = [...document.querySelectorAll(sel)].find((e) => !text || e.textContent.includes(text));
    return el ? (inner ? el.querySelector(inner) : el) : null;
  }, sel, text, inner || "");
  const el = h.asElement();
  if (!el) throw new Error("not found: " + sel + " " + (text || ""));
  await el.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await el.click();
}
async function ask(page, text) { await page.click("#draft"); await page.type("#draft", text); await page.click("#send"); }
async function approve(browser, page) {
  await waitFor(page, () => document.querySelector("#convo .msg.system a.btn"));
  const href = await page.$eval("#convo .msg.system a.btn", (a) => a.getAttribute("href"));
  ok(new URL(href).origin === BASE && href.includes("/practice/checkoutnow"), "approval page is on the same port under /practice: " + href);
  const tabP = new Promise((res) => browser.once("targetcreated", (t) => res(t.page())));
  await page.click("#convo .msg.system a.btn");
  const tab = await tabP;
  await tab.bringToFront();
  await tab.waitForSelector("button");
  ok((await tab.content()).includes("Practice server"), "approval page says it is a practice server");
  await clickIn(tab, "button", "Approve the hold");
  await sleep(1200);
  await tab.close().catch(() => {});
  await page.bringToFront();
}

async function visitor(browser, name) {
  const ctxt = await browser.createBrowserContext();   // own cookie jar
  const page = await ctxt.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto(BASE + "/", { waitUntil: "networkidle2" });
  const bar = await page.$eval("#judgebar", (e) => e.textContent);
  ok(bar.includes("recorded model") && bar.includes("Test money"), name + ": judge-mode line is visible");
  await clickIn(page, "a.stall.newstall").catch(() => {});
  await sleep(500);
  await clickIn(page, ".pick", "Account Brief", ".btn.go2");
  await waitFor(page, () => location.pathname.startsWith("/chats/"));
  await sleep(500);
  await waitFor(page, () => [...document.querySelectorAll("#sidebody li")].some((e) => e.textContent.includes("Work")), 20000);
  await clickIn(page, "#sidebody li", "Work", ".twist"); await sleep(300);
  await clickIn(page, "#sidebody li", "Accounts", ".twist"); await sleep(300);
  await clickIn(page, "#sidebody li", "Initech", "input[type=checkbox]"); await sleep(600);
  return page;
}

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox"] });
try {
  const [a, b] = [await visitor(browser, "A"), await visitor(browser, "B")];
  await ask(a, "Which accounts are at risk?");
  await approve(browser, a);
  await waitFor(a, () => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 1, 90000);
  const ans = await a.$eval("#convo .msg.helper", (e) => e.textContent);
  ok(/Initech/.test(ans), "A: answer names Initech: " + ans.slice(0, 90).replace(/\s+/g, " "));
  ok(await a.$eval("#convo", (e) => /Written from [0-9]+ of your files/.test(e.textContent)), "A: the list of files the answer is based on is shown");
  await a.click("#coinbtn"); await sleep(800);
  await clickIn(a, "#wallet *", "What happened").catch(() => {});
  await sleep(500);
  ok((await a.$eval("#wallet", (e) => e.textContent)).includes("25¢ of the 40¢ hold"), "A: receipt shows '25¢ of the 40¢ hold'");
  await a.click("#wallet [data-close]"); await sleep(400);

  // B never asked anything: it must not see A's chat or A's payments
  await b.reload({ waitUntil: "networkidle2" });
  const bChats = await b.evaluate(async () => (await (await fetch("/api/state")).json()).threads.length);
  const bPay = await b.evaluate(async () => (await (await fetch("/api/state")).json()).payments.captured);
  ok(bChats <= 1 && bPay === 0, `B sees none of A's activity (chats ${bChats}, captured ${bPay})`);
  const aId = a.url().split("/chats/")[1];
  const leak = await b.evaluate(async (id) => (await fetch("/api/thread?id=" + id)).status, aId);
  ok(leak >= 400, "B cannot open A's chat by its address (status " + leak + ")");

  await ask(a, "And which one is the biggest?");     // carrying on = accepted
  await approve(browser, a);
  await waitFor(a, () => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 2, 90000);
  await a.click("#coinbtn"); await sleep(800);
  ok(/Paid/.test(await a.$eval("#walletbody", (e) => e.textContent)), "A: first answer is paid after carrying on");
  await a.click("#wallet [data-close]"); await sleep(400);
  await clickIn(a, "#convo button.linkbtn", "Not helpful"); await sleep(1200);
  await a.click("#coinbtn"); await sleep(800);
  await clickIn(a, "#wallet *", "What happened").catch(() => {});
  ok((await a.$eval("#wallet", (e) => e.textContent)).includes("deposit only"), "A: 'Not helpful' keeps the deposit only");

  // B runs its own flow independently
  await b.goto(BASE + "/", { waitUntil: "networkidle2" });
  await clickIn(b, "a.stall.newstall").catch(() => {}); await sleep(500);
  await clickIn(b, ".pick", "Account Brief", ".btn.go2");
  await waitFor(b, () => location.pathname.startsWith("/chats/")); await sleep(500);
  await waitFor(b, () => [...document.querySelectorAll("#sidebody li")].some((e) => e.textContent.includes("Work")), 20000);
  await clickIn(b, "#sidebody li", "Work", ".twist"); await sleep(300);
  await clickIn(b, "#sidebody li", "Accounts", ".twist"); await sleep(300);
  await clickIn(b, "#sidebody li", "Initech", "input[type=checkbox]"); await sleep(600);
  await ask(b, "Which accounts are at risk?");
  await approve(browser, b);
  await waitFor(b, () => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 1, 90000);
  const bPay2 = await b.evaluate(async () => (await (await fetch("/api/state")).json()).payments);
  const aPay2 = await a.evaluate(async () => (await (await fetch("/api/state")).json()).payments);
  ok(bPay2.captured !== undefined && JSON.stringify(bPay2) !== JSON.stringify(aPay2), "B has its own ledger: " + JSON.stringify({ A: aPay2.captured, B: bPay2.captured }));
  if (process.env.JUDGE_SHOT) await a.screenshot({ path: process.env.JUDGE_SHOT });
} finally {
  await browser.close();
}
console.log(failed ? `${failed} check(s) failed` : "all checks passed");
process.exit(failed ? 1 : 0);
