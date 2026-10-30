/* One chat as a market stall: an awning, a tiny office drawn on a canvas that reflects what the helper is doing, and a few facts.
   The canvases are redrawn by one shared animation loop. */
import { K, person, lookFor } from "../pixel/office.js";
import { el, link } from "../lib/dom.js";
import { hash, cents } from "../lib/format.js";
import { paths } from "../lib/nav.js";

const AWNINGS = ["coral", "mint", "sky", "lemon", "lilac", "peach"];
export const STATE_TEXT = { working: "Working", waiting: "Waiting for you", stopped: "Stopped by the guard", idle: "Answered", new: "Ready" };
const W = 56, H = 40;
const sprites = new Set();
let raf = 0;

const px = (c, x, y, w, h, col) => { c.fillStyle = col; c.fillRect(Math.round(x), Math.round(y), w, h); };
const box = (c, x, y, w, h, fill) => { px(c, x - 1, y - 1, w + 2, h + 2, K.ink); px(c, x, y, w, h, fill); };

function paint(cv, t) {
  const c = cv.getContext("2d"), k = K, st = cv._state || "new", agent = cv._agent || { id: "x", status: "certified" };
  c.imageSmoothingEnabled = false;
  px(c, 0, 0, W, H, k.cream200); px(c, 0, 31, W, 9, k.wood); px(c, 0, 31, W, 1, k.woodD);
  px(c, 3, 3, 10, 8, k.skyL); px(c, 3, 3, 10, 1, k.ink); px(c, 8, 3, 1, 8, k.ink);  // a window
  const look = lookFor(agent.id, st === "stopped" ? "flagged" : agent.status);
  const beat = Math.floor(t / 320) % 2;
  const pose = st === "working" ? (beat ? "sit" : "up") : st === "stopped" ? "up" : "idle";
  person(c, 20, st === "working" || st === "stopped" ? 30 : 31, { pose, facing: "f", mood: st === "stopped" ? "bad" : "ok", ...look }, t);  // the desk covers the legs
  box(c, 6, 28, 34, 8, k.woodD); px(c, 6, 28, 34, 2, k.wood);
  box(c, 31, 18, 11, 9, k.ink700);  // the monitor
  px(c, 32, 19, 9, 6, st === "working" ? (beat ? k.mintL : k.skyL) : st === "stopped" ? k.coralL : k.skyL);
  if (st === "working") { px(c, 33, 21, 4 + beat * 2, 1, k.ink500); px(c, 33, 23, 6 - beat * 2, 1, k.ink500); }
  if (st === "waiting") { const y = 6 + (beat ? 1 : 0); box(c, 18, y, 5, 5, k.lemon); px(c, 19, y + 1, 1, 1, k.cream50); }  // a coin: it waits for your approval
  if (st === "stopped") { const on = Math.floor(t / 220) % 2; box(c, 44, 22, 6, 6, on ? k.coral : k.coralL); px(c, 43, 28, 8, 2, k.ink); }
  if (st === "idle" && cv._answered) { box(c, 12, 25, 8, 4, k.cream50); px(c, 13, 26, 6, 1, k.ink300); }  // an answer lies on the desk
}

function loop(ts) {
  sprites.forEach((cv) => { if (!cv.isConnected) sprites.delete(cv); else paint(cv, ts); });
  raf = sprites.size ? requestAnimationFrame(loop) : 0;
}

function watch(cv) {
  sprites.add(cv);
  if (!raf) raf = requestAnimationFrame(loop);
}

const chip = (text, cls) => el("span", "chip " + (cls || ""), text);

/** A stall for one chat (`s` is a row of /api/office). It is a real link, so it can be opened in a new tab. */
export function stallCard(s) {
  const card = link(paths.chat(s.id), "", "stall state-" + s.state);
  const awn = el("div", "awning");
  awn.style.setProperty("--awn", "var(--" + AWNINGS[hash(s.agent.id) % AWNINGS.length] + ")");
  const cv = el("canvas");
  cv.width = W; cv.height = H; cv._state = s.state; cv._agent = s.agent; cv._answered = s.messages > 1;
  cv.setAttribute("aria-hidden", "true");
  const top = el("div", "stop");
  top.append(el("span", "lamp"), el("span", "swhat", STATE_TEXT[s.state] || s.state));
  card.append(awn, cv, top, el("div", "sname", s.title), el("div", "shelper", "with " + s.agent.name), el("div", "sline", s.line));
  const meta = el("div", "sbadges");
  meta.append(chip(s.shelf_count ? "Opens " + s.shelves.join(", ") + (s.shelf_count > s.shelves.length ? " +" + (s.shelf_count - s.shelves.length) : "") : "No shelves open", s.shelf_count ? "" : "calm"));
  meta.append(chip(cents(s.spent) + " spent" + (s.held ? ", " + cents(s.held) + " on hold" : "")));
  card.append(meta);
  card.setAttribute("aria-label", `${s.title}, with ${s.agent.name}. ${STATE_TEXT[s.state] || ""}. ${s.line}`);
  watch(cv);
  return card;
}
