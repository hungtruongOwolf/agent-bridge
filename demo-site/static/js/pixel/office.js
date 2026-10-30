/* The office floor: a small pixel-art world drawn entirely by this file (no borrowed art).
 * World is 320 x 200 "game pixels", scaled by a whole number so edges stay crisp. Text is drawn on top at screen size.
 * Style and palette follow munder-difflin's design system (MIT). See NOTICE.
 *
 * The story it tells is the REAL run record: Office.play(report) walks the journal entry by entry.
 */
import { hash } from "../lib/format.js";

const W = 320, H = 200;
const K = {
  cream50: "#FFFDF5", cream100: "#FFF8E7", cream200: "#F4E9C7", cream300: "#E8D9A0",
  ink: "#1A1320", ink700: "#3D2E4A", ink500: "#6B5878", ink300: "#A899B5", ink100: "#D9CFE0",
  coral: "#D96A62", coralL: "#F3D3CD", mint: "#5CA97A", mintL: "#D2E7DA", sky: "#4F9FAF", skyL: "#CFE5E9",
  lemon: "#DCAB3C", lemonL: "#F3E4BC", lilac: "#9482D3", lilacL: "#E0DAF2", peach: "#D99168",
  grass: "#D4EAB0", grassD: "#B5D589", wood: "#E5C896", woodD: "#C9A66B", wall: "#8B6F47", path: "#E8D8B0"
};
const SHIRTS = [K.coral, K.mint, K.sky, K.lemon, K.lilac, K.peach];
const HATS = ["visor", "cap", "glasses", "headset", "hard", "wizard"];
const SKINS = ["#F5CBA7", "#E0AC82", "#C68642", "#8D5524"];
const HAIRS = ["#3B2A20", "#1A1320", "#8A5A2B", "#C9A66B"];

// places on the floor (world pixels)
const P = {
  youSeat: [40, 150], jar: [84, 152], cabinetFront: [34, 128], door: [97, 130], doorOut: [76, 150], lobby: [80, 160],
  agentSeat: [152, 108], tray: [205, 90], guard: [218, 98], clerkHome: [128, 178], back: [155, 44],
  building: { brain: [240, 28, 68, 42], web: [240, 80, 68, 42], bank: [240, 132, 68, 42] },
  exit: [228, 0]
};
P.buildingDoor = { brain: [232, 56], web: [232, 108], bank: [232, 160] };

function lookFor(id, status) {
  const h = hash(id || "x");
  return { shirt: SHIRTS[h % 6], hat: HATS[(h >> 3) % 6], skin: SKINS[(h >> 6) % 4], hair: HAIRS[(h >> 9) % 4],
           badge: status === "certified", mask: status === "flagged", stripes: status === "flagged" };
}

// ---------- drawing helpers (world pixels) ----------
function px(c, x, y, w, h, col) { c.fillStyle = col; c.fillRect(Math.round(x), Math.round(y), w, h); }
function box(c, x, y, w, h, fill, line) { px(c, x - 1, y - 1, w + 2, h + 2, line || K.ink); px(c, x, y, w, h, fill); }

/* A person, feet at (x, y). pose: idle | walk | sit | up. facing: l | r | f */
function person(c, x, y, o, t) {
  const pose = o.pose || "idle", sit = pose === "sit", up = pose === "up";
  const step = pose === "walk" ? (Math.floor(t / 140) % 2) : 0;
  const bob = pose === "idle" ? (Math.floor(t / 500) % 2) : 0;
  const dy = (sit ? 7 : 0) - (bob ? 1 : 0);
  const X = Math.round(x), Y = Math.round(y) + dy;
  const rects = [];                                      // [x, y, w, h, colour]
  const add = (rx, ry, w, h, col) => rects.push([X + rx, Y + ry, w, h, col]);
  // legs and shoes
  if (!sit) {
    add(-3, -9, 3, 6 - (step ? 1 : 0), o.pants || K.ink700); add(1, -9, 3, 6 - (step ? 0 : 1), o.pants || K.ink700);
    add(-3, -3 - (step ? 1 : 0), 3, 2, K.ink); add(1, -3 - (step ? 0 : 1), 3, 2, K.ink);
  }
  // body, arms
  add(-4, -16, 9, 8, o.shirt || K.sky);
  if (o.stripes) { add(-4, -14, 9, 1, K.ink); add(-4, -11, 9, 1, K.ink); }
  const armY = up ? -20 : -15, armH = up ? 5 : 6;
  add(-6, armY, 2, armH, o.skin || SKINS[0]); add(5, armY, 2, armH, o.skin || SKINS[0]);
  // head and hair
  add(-3, -22, 7, 6, o.skin || SKINS[0]);
  add(-3, -22, 7, 2, o.hair || HAIRS[0]);
  // outline pass first, then colours
  for (const r of rects) px(c, r[0] - 1, r[1] - 1, r[2] + 2, r[3] + 2, K.ink);
  for (const r of rects) px(c, r[0], r[1], r[2], r[3], r[4]);
  // face
  const fx = o.facing === "l" ? -1 : o.facing === "r" ? 1 : 0;
  px(c, X - 2 + fx, Y - 19, 1, 2, K.ink); px(c, X + 1 + fx, Y - 19, 1, 2, K.ink);
  if (o.mood === "bad") px(c, X - 1 + fx, Y - 17, 3, 1, K.ink);
  // hat / accessory
  const hat = o.hat;
  if (hat === "cap") { px(c, X - 4, Y - 24, 9, 3, K.coral); px(c, X + 2 * (fx || 1), Y - 22, 4, 1, K.coral); }
  else if (hat === "visor") px(c, X - 4, Y - 23, 9, 2, K.lemon);
  else if (hat === "glasses") { px(c, X - 3, Y - 20, 3, 2, K.ink); px(c, X + 1, Y - 20, 3, 2, K.ink); px(c, X, Y - 20, 1, 1, K.ink); }
  else if (hat === "headset") { px(c, X - 4, Y - 22, 1, 4, K.ink); px(c, X + 4, Y - 22, 1, 4, K.ink); px(c, X - 4, Y - 23, 9, 1, K.ink); }
  else if (hat === "hard") { px(c, X - 4, Y - 24, 9, 3, K.lemon); px(c, X - 5, Y - 22, 11, 1, K.lemon); }
  else if (hat === "wizard") { px(c, X - 3, Y - 24, 7, 2, K.lilac); px(c, X - 2, Y - 27, 5, 3, K.lilac); px(c, X - 1, Y - 29, 3, 2, K.lilac); }
  else if (hat === "guard") { px(c, X - 4, Y - 24, 9, 3, K.ink700); px(c, X - 1, Y - 24, 3, 2, K.lemon); }
  if (o.mask) px(c, X - 3, Y - 20, 7, 2, K.ink);
  if (o.badge) { px(c, X + 1, Y - 14, 3, 3, K.cream50); px(c, X + 2, Y - 13, 1, 1, K.mint); }
}

function desk(c, x, y, w) {
  box(c, x, y, w, 10, K.woodD); px(c, x, y, w, 3, K.wood);
  box(c, x + 4, y - 9, 12, 9, K.ink700); px(c, x + 5, y - 8, 10, 6, K.skyL);   // monitor
}

function drawer(c, x, y, d, t) {
  const shake = d.shake > 0 ? (Math.floor(t / 60) % 2 ? 2 : -2) : 0;
  const ox = (d.open ? 5 : 0) + shake;
  if (d.open) { px(c, x + 2, y + 1, 40, 12, K.ink); px(c, x + 3, y - 1, 7, 3, K.lemonL); px(c, x + 14, y - 1, 7, 3, K.mintL); px(c, x + 25, y - 1, 7, 3, K.skyL); }
  box(c, x + ox, y, 40, 12, d.hot ? K.coralL : (d.open ? K.mintL : K.cream200));
  px(c, x + ox + 15, y + 5, 10, 2, K.ink);                                           // handle
  if (d.locked) { box(c, x + ox + 28, y + 2, 8, 8, K.lemon); px(c, x + ox + 30, y - 1, 4, 3, K.ink); px(c, x + ox + 31, y + 4, 2, 3, K.ink); }
  if (d.count != null) for (let i = 0; i < Math.min(d.count, 5); i++) px(c, x + ox + 3 + i * 3, y + 3, 2, 6, d.open ? K.mint : K.ink300);
}

function building(c, b, kind, lit) {
  const [x, y, w, h] = b;
  box(c, x, y, w, h, lit ? K.lemonL : K.cream200);
  px(c, x, y, w, 8, kind === "bank" ? K.mint : kind === "brain" ? K.coral : K.sky);
  for (let i = 0; i < 4; i++) px(c, x + 6 + i * 15, y + 16, 8, 8, lit ? K.lemon : K.skyL);
  px(c, x + w / 2 - 5, y + h - 14, 10, 14, K.woodD);
  if (kind === "brain") {  // a pink brain on the roof: two lobes with folds
    const rows = [[5, 6], [3, 10], [2, 12], [1, 14], [1, 14], [2, 12], [3, 10], [5, 6]], bx = x + w / 2 - 8, by = y - 12;
    rows.forEach((r, i) => px(c, bx + r[0] - 1, by + i - 1, r[1] + 2, 3, K.ink));
    rows.forEach((r, i) => px(c, bx + r[0], by + i, r[1], 1, K.coralL));
    px(c, bx + 8, by, 1, 8, K.ink); px(c, bx + 4, by + 2, 3, 1, K.coral); px(c, bx + 10, by + 2, 3, 1, K.coral); px(c, bx + 3, by + 5, 4, 1, K.coral); px(c, bx + 10, by + 5, 4, 1, K.coral);
    if (lit) { px(c, bx - 3, by + 2, 2, 2, K.lemon); px(c, bx + 18, by + 2, 2, 2, K.lemon); }
  }
  if (kind === "bank") { px(c, x + 4, y + 30, w - 8, 3, K.ink700); }
}

function coin(c, x, y) { box(c, x - 2, y - 2, 4, 4, K.lemon, K.ink); px(c, x - 1, y - 1, 1, 1, K.cream50); }
function letter(c, x, y, col) { box(c, x - 4, y - 3, 8, 6, col || K.cream50); px(c, x - 3, y - 2, 6, 1, K.ink300); px(c, x - 1, y, 2, 1, K.ink300); }
function folder(c, x, y, col) { box(c, x - 4, y - 3, 9, 7, col || K.lemon); px(c, x - 4, y - 5, 4, 2, col || K.lemon); px(c, x - 4, y - 5, 4, 1, K.ink); }
function paper(c, x, y) { box(c, x - 3, y - 4, 7, 8, K.cream50); px(c, x - 2, y - 2, 5, 1, K.ink300); px(c, x - 2, y, 5, 1, K.ink300); }
function plane(c, x, y) { px(c, x - 4, y, 8, 2, K.cream50); px(c, x - 4, y - 1, 8, 1, K.ink); px(c, x - 4, y + 2, 8, 1, K.ink); px(c, x + 3, y - 1, 2, 4, K.ink); }
function siren(c, x, y, on) { box(c, x - 3, y - 5, 7, 6, on ? K.coral : K.coralL); px(c, x - 4, y + 1, 9, 2, K.ink); }

/* ---------- the scene ---------- */
class Office {
  constructor(canvas, hooks) {
    this.canvas = canvas; this.hooks = hooks || {};
    this.world = document.createElement("canvas"); this.world.width = W; this.world.height = H;
    this.w = this.world.getContext("2d"); this.ctx = canvas.getContext("2d");
    this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.items = []; this.tweens = []; this.bubbles = {}; this.token = 0; this.t = 0; this.last = 0;
    this.S = 3; this.dpr = 1; this.pace = 1.8;  // >1 means faster
    this.reset();
    this.resize();
    canvas.addEventListener("click", (e) => this.click(e));
    canvas.addEventListener("mousemove", (e) => { const d = this.drawerAt(e); canvas.style.cursor = d ? "pointer" : "default"; });
    window.addEventListener("resize", () => this.resize());
    requestAnimationFrame((ts) => this.frame(ts));
  }

  reset() {
    this.you = { x: P.youSeat[0], y: P.youSeat[1], pose: "sit", facing: "r", shirt: K.mint, hat: "cap", skin: SKINS[1], hair: HAIRS[1], name: "You" };
    this.agent = null; this.agentLook = null;
    this.guard = { x: P.guard[0], y: P.guard[1], pose: "idle", facing: "l", shirt: K.ink700, pants: K.ink, hat: "guard", skin: SKINS[0], hair: HAIRS[1], name: "Guard" };
    this.clerk = { x: P.clerkHome[0], y: P.clerkHome[1], pose: "idle", facing: "r", shirt: K.peach, hat: "visor", skin: SKINS[2], hair: HAIRS[0], name: "Assistant" };
    this.items = []; this.tweens = []; this.bubbles = {}; this.sirenOn = false; this.lit = {}; this.counters = {};
    this.drawers = this.drawers || [];
    this.drawers.forEach((d) => { d.shake = 0; d.hot = false; });
    this.stampText = null; this.deskFiles = 0; this.hold = 0; this.flash = 0; this.glassHit = 0; this.backDoorHit = 0; this.scribble = 0;
  }

  // ----- public setters -----
  setAgent(a) {  // {id, name, status}
    this.agentInfo = a || null;
    if (!a) { this.agent = null; return; }
    const look = lookFor(a.id, a.status);
    this.agent = Object.assign({ x: P.lobby[0], y: P.lobby[1], pose: "idle", facing: "r", name: a.name }, look);
  }
  setDrawers(list) { // [{type,label,count,open,locked}]
    const old = this.drawers || [];
    this.drawers = list.map((d, i) => Object.assign({ shake: 0, hot: false }, old[i] && old[i].type === d.type ? { shake: old[i].shake, hot: old[i].hot } : {}, d));
  }
  setHold(cents) { this.hold = cents; }
  say(who, text, ms) { this.bubbles[who] = { text, until: ms ? this.t + ms : Infinity }; }
  hush(who) { delete this.bubbles[who]; }

  resize() {
    const parent = this.canvas.parentElement; const avail = Math.max(320, parent.clientWidth - 16);
    this.S = Math.max(1, Math.floor(avail / W)); this.dpr = Math.max(1, Math.round(window.devicePixelRatio || 1));
    this.f = this.S * this.dpr;                                         // whole-number scale: pixel edges stay crisp
    this.canvas.width = W * this.f; this.canvas.height = H * this.f;
    this.canvas.style.width = (W * this.S) + "px"; this.canvas.style.height = (H * this.S) + "px";
  }

  // ----- timing -----
  sleep(ms) {
    const tok = this.token;
    if (this.reduced || this.fast) return Promise.resolve();
    return new Promise((res, rej) => setTimeout(() => (tok === this.token ? res() : rej(new Error("cancelled"))), ms / this.pace));
  }
  tween(obj, props, ms) {
    const tok = this.token;
    if (this.reduced || this.fast || ms <= 0) { Object.assign(obj, props); return Promise.resolve(); }
    return new Promise((res, rej) => {
      const from = {}; for (const k in props) from[k] = obj[k];
      this.tweens.push({ obj, from, to: props, start: this.t, ms: ms / this.pace, res, rej, tok });
    });
  }
  walk(p, x, y, speed) {
    const d = Math.hypot(p.x - x, p.y - y);
    if (d < 1) return Promise.resolve();
    p.facing = x > p.x ? "r" : "l"; p.pose = "walk";
    return this.tween(p, { x, y }, d / (speed || 60) * 1000).then(() => { p.pose = "idle"; });
  }
  async path(p, pts, speed) { for (const q of pts) await this.walk(p, q[0], q[1], speed); }
  fly(item, to, ms, arc) {
    this.items.push(item);
    const tok = this.token, sx = item.x, sy = item.y;
    if (this.reduced || this.fast) { item.x = to[0]; item.y = to[1]; return Promise.resolve(item); }
    return new Promise((res, rej) => this.tweens.push({ item, sx, sy, to, arc: arc || 0, start: this.t, ms: ms / this.pace, res: () => res(item), rej, tok, fly: true }));
  }
  drop(item) { this.items = this.items.filter((i) => i !== item); }

  frame(ts) {
    const dt = this.last ? ts - this.last : 16; this.last = ts; this.t += dt;
    for (const tw of this.tweens.slice()) {
      if (tw.tok !== this.token) { this.tweens.splice(this.tweens.indexOf(tw), 1); tw.rej(new Error("cancelled")); continue; }
      const k = Math.min(1, (this.t - tw.start) / tw.ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      if (tw.fly) { tw.item.x = tw.sx + (tw.to[0] - tw.sx) * e; tw.item.y = tw.sy + (tw.to[1] - tw.sy) * e - tw.arc * Math.sin(Math.PI * k); }
      else for (const p in tw.to) tw.obj[p] = tw.from[p] + (tw.to[p] - tw.from[p]) * e;
      if (k >= 1) { this.tweens.splice(this.tweens.indexOf(tw), 1); tw.res(); }
    }
    for (const d of this.drawers) if (d.shake > 0) d.shake = Math.max(0, d.shake - dt);
    if (this.flash > 0) this.flash = Math.max(0, this.flash - dt);
    if (this.glassHit > 0) this.glassHit = Math.max(0, this.glassHit - dt);
    this.draw();
    requestAnimationFrame((n) => this.frame(n));
  }

  // ----- drawing -----
  draw() {
    const c = this.w, t = this.t;
    // outside grass and the building floor
    px(c, 0, 0, W, H, K.grass);
    for (let y = 0; y < H; y += 8) for (let x = 0; x < W; x += 8) if (((x + y) / 8) % 2 === 0 && x > 224) px(c, x, y, 8, 8, K.grassD);
    box(c, 6, 14, 220, 184, K.wood, K.wall); px(c, 6, 14, 220, 12, K.wall);
    for (let y = 26; y < 198; y += 8) for (let x = 7; x < 225; x += 8) if (((x - 7) / 8 + (y - 26) / 8) % 2 === 0) px(c, x, y, 8, 8, K.woodD);
    px(c, 226, 26, 14, 172, K.path);                                    // path to the buildings
    // buildings
    building(c, P.building.brain, "brain", !!this.lit.brain);
    building(c, P.building.web, "web", !!this.lit.web);
    building(c, P.building.bank, "bank", !!this.lit.bank);
    // your office: cabinet
    box(c, 11, 42, 46, 74, K.cream300);
    this.drawers.slice(0, 4).forEach((d, i) => drawer(c, 14, 46 + i * 17, d, t));
    // your desk and the jar
    desk(c, 22, 150, 52);
    box(c, 80, 140, 10, 14, K.skyL); px(c, 82, 138, 6, 3, K.ink);
    const coins = Math.min(5, Math.ceil(this.hold / 10));
    for (let i = 0; i < coins; i++) coin(c, 85 + (i % 2), 151 - i * 2);
    // glass room (drawn before the agent so the helper is visible through it)
    px(c, 99, 42, 106, 108, "#DCEFF2");
    for (let i = 0; i < 6; i++) px(c, 104 + i * 18, 48, 2, 8, "#F6FDFE");
    // agent behind the desk
    if (this.agent) person(c, this.agent.x, this.agent.y, this.agent, t);
    { box(c, 130, 105, 46, 11, K.woodD); px(c, 130, 105, 46, 3, K.wood); box(c, 135, 96, 11, 9, K.ink700); px(c, 136, 97, 9, 6, K.skyL);
      for (let i = 0; i < Math.min(this.deskFiles || 0, 4); i++) folder(c, 156 + i * 5, 106, i % 2 ? K.mint : K.lemon);
      box(c, 104, 128, 14, 8, K.cream200); px(c, 104, 128, 14, 2, K.lilac);              // a plant corner and a rug make it a room
      box(c, 180, 118, 18, 12, K.cream200); px(c, 183, 121, 12, 1, K.ink300); px(c, 183, 124, 12, 1, K.ink300); }
    // glass walls (door gap on the left, tray window on the right)
    const wallCol = this.glassHit > 0 ? K.coral : K.ink;
    px(c, 97, 40, 110, 3, wallCol); px(c, 97, 40, 3, 90, wallCol); px(c, 97, 144, 3, 8, wallCol); px(c, 97, 150, 110, 3, wallCol); px(c, 204, 40, 3, 112, wallCol);
    px(c, 97, 130, 3, 14, this.doorOpen ? K.skyL : K.woodD);
    box(c, 202, 84, 7, 12, K.lemonL);                                    // inspection tray
    box(c, 150, 38, 12, 4, this.backDoorHit > 0 ? K.coral : K.woodD);      // the room's back door (never opens)
    // guard and the inspection desk
    box(c, 210, 100, 14, 8, K.woodD);
    if (this.stampText) { box(c, 212, 92, 10, 7, this.stampText === "ok" ? K.mint : K.coral); }
    person(c, this.guard.x, this.guard.y, this.guard, t);
    if (this.sirenOn) siren(c, this.guard.x, this.guard.y - 27, Math.floor(t / 200) % 2 === 0);
    // assistant and you
    person(c, this.clerk.x, this.clerk.y, this.clerk, t);
    if (this.clerk.carry) letter(c, this.clerk.x, this.clerk.y - 27, this.clerk.carry);
    person(c, this.you.x, this.you.y, this.you, t);
    // flying things
    for (const it of this.items) {
      if (it.kind === "coin") coin(c, it.x, it.y); else if (it.kind === "letter") letter(c, it.x, it.y, it.col);
      else if (it.kind === "folder") folder(c, it.x, it.y, it.col); else if (it.kind === "paper") paper(c, it.x, it.y);
      else if (it.kind === "plane") plane(c, it.x, it.y);
      else if (it.kind === "spark") { px(c, it.x - 1, it.y - 3, 2, 6, K.lemon); px(c, it.x - 3, it.y - 1, 6, 2, K.lemon); }
    }
    if (this.scribble > 0) { px(c, 214, 130, 14, 1, K.coral); px(c, 216, 133, 12, 1, K.coral); px(c, 212, 136, 14, 1, K.coral); }
    if (this.flash > 0) { c.globalAlpha = Math.min(.35, this.flash / 800); px(c, 0, 0, W, H, K.coral); c.globalAlpha = 1; }

    // ---- screen layer: scale the world up, then write text at screen resolution ----
    const g = this.ctx, f = this.f;
    g.imageSmoothingEnabled = false; g.clearRect(0, 0, this.canvas.width, this.canvas.height);
    g.drawImage(this.world, 0, 0, W * f, H * f);
    this.labels(g, f);
  }

  labels(g, f) {
    const dpr = this.dpr, big = this.S >= 2;
    const label = (txt, wx, wy, align) => {
      g.font = (8 * dpr) + "px 'Press Start 2P', monospace"; g.textAlign = align || "left"; g.textBaseline = "middle";
      const w = g.measureText(txt).width; const x = wx * f - (align === "center" ? w / 2 : 0), y = wy * f;
      g.fillStyle = K.cream100; g.fillRect(x - 4 * dpr, y - 8 * dpr, w + 8 * dpr, 16 * dpr);
      g.strokeStyle = K.ink; g.lineWidth = 2 * dpr; g.strokeRect(x - 4 * dpr, y - 8 * dpr, w + 8 * dpr, 16 * dpr);
      g.fillStyle = K.ink; g.textAlign = "left"; g.fillText(txt, x, y + dpr);
    };
    if (big) {
      label("Your office", 12, 20); label("Glass room", 100, 34); label("Brain", 242, 24); label("Web library", 242, 76); label("Bank", 242, 128);
      this.drawers.slice(0, 4).forEach((d, i) => { if (this.S >= 3) { g.font = (11 * dpr) + "px Inter, sans-serif"; g.textAlign = "left"; g.textBaseline = "middle"; g.fillStyle = K.ink; g.fillText(d.label, 60 * f, (52 + i * 17) * f); } });
      if (this.hold > 0) { g.font = (11 * dpr) + "px Inter, sans-serif"; g.fillStyle = K.ink; g.textAlign = "left"; g.fillText("On hold: " + this.hold + "c", 62 * f, 166 * f); }
      for (const k in this.counters) { const [x, y] = k === "brain" ? [250, 62] : k === "web" ? [250, 114] : [250, 166]; g.font = (10 * dpr) + "px Inter, sans-serif"; g.fillStyle = K.ink; g.textAlign = "left"; g.textBaseline = "middle"; g.fillText(this.counters[k], x * f, y * f); }
      if (this.stampText) { g.font = (8 * dpr) + "px 'Press Start 2P'"; g.fillStyle = this.stampText === "ok" ? "#2f7a4d" : "#9a3a33"; g.textAlign = "center"; g.fillText(this.stampText === "ok" ? "SAFE" : "STOP", 217 * f, 87 * f); }
    }
    // names above characters
    const nm = (p, dy) => { if (!p) return; g.font = (11 * dpr) + "px Inter, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = K.ink; g.fillText(p.name, p.x * f, (p.y + (p.pose === "sit" ? 7 : 0) + dy) * f); };
    if (big) { nm(this.you, 6); nm(this.guard, 6); nm(this.clerk, 6); if (this.agent) nm(this.agent, 6); }
    // speech bubbles
    for (const who in this.bubbles) {
      const b = this.bubbles[who]; if (b.until < this.t) { delete this.bubbles[who]; continue; }
      const p = who === "agent" ? this.agent : this[who]; if (!p) continue;
      this.bubble(g, p.x * f, (p.y + (p.pose === "sit" ? 7 : 0) - 32) * f, b.text, dpr);
    }
  }

  bubble(g, x, y, text, dpr) {
    g.font = (12 * dpr) + "px Inter, sans-serif"; g.textBaseline = "middle";
    const maxW = 170 * dpr, words = text.split(" "), lines = []; let cur = "";
    for (const w of words) { const test = cur ? cur + " " + w : w; if (g.measureText(test).width > maxW && cur) { lines.push(cur); cur = w; } else cur = test; }
    lines.push(cur);
    const lw = Math.max(...lines.map((l) => g.measureText(l).width)), pad = 6 * dpr, lh = 15 * dpr, bw = lw + pad * 2, bh = lines.length * lh + pad * 2;
    let bx = Math.min(Math.max(x - bw / 2, 4), this.canvas.width - bw - 4), by = Math.max(4, y - bh);
    g.fillStyle = K.cream50; g.fillRect(bx, by, bw, bh); g.strokeStyle = K.ink; g.lineWidth = 2 * dpr; g.strokeRect(bx, by, bw, bh);
    g.fillStyle = K.ink; g.beginPath(); g.moveTo(x - 4 * dpr, by + bh); g.lineTo(x + 4 * dpr, by + bh); g.lineTo(x, by + bh + 6 * dpr); g.fill();
    g.textAlign = "left"; lines.forEach((l, i) => g.fillText(l, bx + pad, by + pad + lh * (i + .5)));
  }

  // ----- clicking the drawers lets you open or close them -----
  drawerAt(e) {
    const r = this.canvas.getBoundingClientRect(), wx = (e.clientX - r.left) / r.width * W, wy = (e.clientY - r.top) / r.height * H;
    if (wx < 11 || wx > 60) return null;
    const i = Math.floor((wy - 46) / 17); return i >= 0 && i < this.drawers.length && wy - 46 - i * 17 < 13 ? this.drawers[i] : null;
  }
  click(e) { const d = this.drawerAt(e); if (d && this.hooks.onDrawer) this.hooks.onDrawer(d.type); }
}

export { Office, person, lookFor, K };
