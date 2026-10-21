/* Records the real console while a script drives it like a person: a visible cursor that glides, clicks that ripple, typing at a human pace.

   const rec = await Recorder.open({ base: "http://127.0.0.1:8787" });
   await rec.start("n03");  ...steps...  await rec.stop();     -> video-out/rec-n03.mp4 and rec-n03.marks.json

   The picture is the browser's own screencast (every change of the page, with its real time), turned into a steady 30 frames a second.
   `rec.mark(name)` notes a moment (such as "answer arrived") so the edit can speed through waits and keep the good parts. */
import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const OUT = resolve(HERE, "../../video-out");
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PACE = parseFloat(process.env.PACE || "0.8");   // below 1 = a little brisker than a relaxed person, so less has to be cut later
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms * PACE));
const real = (ms) => new Promise((r) => setTimeout(r, ms));

const CURSOR = `(() => {
  const mk = () => {
    if (document.getElementById("__cur")) return;
    const c = document.createElement("div");
    c.id = "__cur";
    c.style.cssText = "position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);transition:none";
    c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M4 2 L4 22 L9 17 L13 26 L17 24 L13 15 L20 15 Z" fill="#1A1320" stroke="#FFFDF5" stroke-width="2" stroke-linejoin="round"/></svg>';
    document.documentElement.append(c);
    const st = document.createElement("style");
    st.textContent = "@keyframes __rip{from{transform:translate(-50%,-50%) scale(.3);opacity:.9}to{transform:translate(-50%,-50%) scale(1.6);opacity:0}}";
    document.head.append(st);
    addEventListener("mousemove", (e) => { c.style.transform = "translate(" + e.clientX + "px," + e.clientY + "px)"; }, true);
    addEventListener("mousedown", (e) => {
      const r = document.createElement("div");
      r.style.cssText = "position:fixed;left:" + e.clientX + "px;top:" + e.clientY + "px;width:46px;height:46px;border-radius:50%;border:4px solid #DCAB3C;z-index:2147483646;pointer-events:none;animation:__rip .5s ease-out forwards";
      document.documentElement.append(r); setTimeout(() => r.remove(), 600);
    }, true);
  };
  if (document.readyState !== "loading") mk(); else document.addEventListener("DOMContentLoaded", mk);
})();`;

export class Recorder {
  static async open({ base, width = 1600, height = 900, scale = 1.2 }) {
    const r = new Recorder();
    r.base = base;
    r.browser = await puppeteer.launch({ executablePath: CHROME, headless: "new", args: ["--no-sandbox", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required"], defaultViewport: null });
    r.size = { width, height, scale };
    r.page = await r.browser.newPage();
    await r.prepare(r.page);
    r.mouse = { x: width / 2, y: height / 2 };
    return r;
  }

  async prepare(page) {
    await page.setViewport({ width: this.size.width, height: this.size.height, deviceScaleFactor: this.size.scale });
    await page.evaluateOnNewDocument(CURSOR);
    page.on("pageerror", (e) => console.error("page error:", e.message));
    page.on("dialog", (d) => d.dismiss());
  }

  /** Run an action that opens a new tab (a link with target=_blank) and return that tab, ready to be recorded. */
  async newTab(action) {
    const got = new Promise((ok) => this.browser.once("targetcreated", async (t) => ok(await t.page())));
    await action();
    const p = await got;
    await this.prepare(p);
    await p.bringToFront();
    await p.waitForSelector("body");
    await p.evaluate(CURSOR);
    await p.evaluate(() => document.fonts.ready);
    return p;
  }

  /** From now on the picture shows this page (a person switching tabs). */
  async switchTo(page) {
    await this.detach();
    this.page = page;
    await page.bringToFront();
    this.mouse = { x: this.size.width / 2, y: this.size.height / 2 };
    await this.attach(page);
  }

  async goto(path) {
    await this.page.goto(this.base + path, { waitUntil: "networkidle0" });
    await this.page.evaluate(() => document.fonts.ready);
  }

  /* ---------- recording ---------- */
  async start(name) {
    this.name = name;
    this.frames = [];
    this.marks = [];
    this.dir = join(OUT, `frames-${name}`);
    await rm(this.dir, { recursive: true, force: true });
    await mkdir(this.dir, { recursive: true });
    this.pending = [];
    await this.attach(this.page);
    await real(150);
    this.t0 = Date.now();
    this.mark("start");
  }

  async attach(page) {
    this.client = await page.createCDPSession();
    this.client.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
      const i = this.frames.length;
      this.frames.push(metadata.timestamp);
      this.pending.push(writeFile(join(this.dir, `f${String(i).padStart(6, "0")}.jpg`), Buffer.from(data, "base64")));
      this.client.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
    });
    await this.client.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  }

  async detach() {
    try { await this.client.send("Page.stopScreencast"); await this.client.detach(); } catch (e) { /* the page may already be gone */ }
  }

  mark(label) { this.marks.push({ label, t: +((Date.now() - this.t0) / 1000).toFixed(3) }); }

  async stop() {
    await real(500);
    await this.detach();
    await Promise.all(this.pending);
    const out = join(OUT, `rec-${this.name}.mp4`);
    const lines = [];
    const ts = this.frames, first = ts[0];
    ts.forEach((t, i) => { lines.push(`file 'f${String(i).padStart(6, "0")}.jpg'`, `duration ${((ts[i + 1] ?? t + 0.05) - t).toFixed(4)}`); });
    lines.push(`file 'f${String(ts.length - 1).padStart(6, "0")}.jpg'`);
    await writeFile(join(this.dir, "list.txt"), lines.join("\n"));
    const total = (ts[ts.length - 1] - first) + 0.05;
    await new Promise((ok, bad) => {
      const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", join(this.dir, "list.txt"), "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-crf", "17", "-preset", "medium", out], { stdio: ["ignore", "inherit", "inherit"] });
      ff.on("close", (c) => (c === 0 ? ok() : bad(new Error("ffmpeg " + c))));
    });
    // marks are relative to the first frame so the edit can use them directly
    const shift = (this.t0 / 1000) - first;
    await writeFile(join(OUT, `rec-${this.name}.marks.json`), JSON.stringify({ duration: +total.toFixed(3), marks: this.marks.map((m) => ({ ...m, t: +(m.t + shift).toFixed(3) })) }, null, 1));
    await rm(this.dir, { recursive: true, force: true });
    console.log(`rec-${this.name}.mp4: ${total.toFixed(1)}s, ${ts.length} changes, marks: ${this.marks.map((m) => m.label).join(", ")}`);
  }

  async close() { await this.browser.close(); }

  /* ---------- acting like a person ---------- */
  async glide(x, y, ms = 650) {
    ms = ms * PACE;
    const { x: sx, y: sy } = this.mouse, steps = Math.max(8, Math.round(ms / 16));
    for (let i = 1; i <= steps; i++) {
      const u = i / steps, e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      await this.page.mouse.move(sx + (x - sx) * e, sy + (y - sy) * e);
      await real(ms / steps);
    }
    this.mouse = { x, y };
  }

  /** Position of the first visible element matching a CSS selector, optionally filtered by its text. */
  async find(sel, text, nth = 0) {
    const h = await this.page.evaluateHandle((sel, text, nth) => {
      const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 2 && r.height > 2 && cs.visibility !== "hidden" && cs.display !== "none"; };
      const all = [...document.querySelectorAll(sel)].filter(vis).filter((e) => !text || (e.textContent || "").trim().toLowerCase().includes(text.toLowerCase()) || (e.getAttribute("aria-label") || "").toLowerCase().includes(text.toLowerCase()));
      return all[nth] || null;
    }, sel, text || "", nth);
    const el = h.asElement();
    if (!el) throw new Error(`not found: ${sel} ${text || ""}`);
    return el;
  }

  async center(el) {
    // scroll only when the thing is not already in view, and do it smoothly so it reads as a person scrolling
    const inView = await el.evaluate((e) => { const r = e.getBoundingClientRect(); return r.top > 70 && r.bottom < innerHeight - 24 && r.left > 0 && r.right < innerWidth; });
    if (!inView) { await el.evaluate((e) => e.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" })); await sleep(950); }
    const b = await el.boundingBox();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  }

  /** Scroll the page smoothly: to the top, or until an element sits near the top of the screen. */
  async scrollTo(sel, text, { block = "start", gap = 90 } = {}) {
    if (!sel) { await this.page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" })); await sleep(1000); return; }
    const el = await this.find(sel, text);
    await el.evaluate((e, block, gap) => { const r = e.getBoundingClientRect(); window.scrollTo({ top: window.scrollY + r.top - (block === "start" ? gap : innerHeight / 2 - r.height / 2), behavior: "smooth" }); }, block, gap);
    await sleep(1000);
  }

  /** An element inside another one found by its text (a twist button inside the row called "Work"). */
  async findIn(containerSel, containerText, innerSel) {
    const h = await this.page.evaluateHandle((c, t, i) => {
      const box = [...document.querySelectorAll(c)].find((e) => (e.textContent || "").trim().toLowerCase().includes(t.toLowerCase()));
      return box ? box.querySelector(i) : null;
    }, containerSel, containerText, innerSel);
    const el = h.asElement();
    if (!el) throw new Error(`not found: ${innerSel} in ${containerSel} ${containerText}`);
    return el;
  }

  async clickEl(el, { ms = 700, after = 500 } = {}) {
    const p = await this.center(el);
    await this.glide(p.x, p.y, ms);
    await sleep(120);
    await this.page.mouse.down(); await sleep(70); await this.page.mouse.up();
    await sleep(after);
  }

  async hover(sel, text, { ms = 700, nth = 0 } = {}) {
    const el = await this.find(sel, text, nth), p = await this.center(el);
    await this.glide(p.x, p.y, ms);
  }

  async click(sel, text, { ms = 700, nth = 0, after = 500 } = {}) {
    const el = await this.find(sel, text, nth), p = await this.center(el);
    await this.glide(p.x, p.y, ms);
    await sleep(120);
    await this.page.mouse.down(); await sleep(70); await this.page.mouse.up();
    await sleep(after);
  }

  async type(text, { delay = 55 } = {}) { await this.page.keyboard.type(text, { delay }); }

  async waitFor(fn, { timeout = 90000, poll = 250, arg } = {}) {
    await this.page.waitForFunction(fn, { timeout, polling: poll }, arg);
  }

  async wheel(x, y, dy, steps = 6, gap = 90) {
    await this.glide(x, y, 500);
    for (let i = 0; i < steps; i++) { await this.page.mouse.wheel({ deltaY: dy / steps }); await sleep(gap); }
  }

  async shot(name) { await this.page.screenshot({ path: join(OUT, `shot-${name}.png`) }); }
}

/** Run one scene module: node record.mjs <scene> [--base url] */
export async function runScene(name, base, fn) {
  await mkdir(OUT, { recursive: true });
  const rec = await Recorder.open({ base });
  try { await fn(rec); } finally { await rec.close(); }
}
