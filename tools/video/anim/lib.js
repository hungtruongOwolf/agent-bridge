/* Shared parts for the animation scenes: the stage (a 320 x 180 pixel world shown at 4x, with real text on top), easing, and
   small pixel sprites in the console's own style. Everything is a pure function of time: draw(t) paints that moment and nothing else. */
import { person, lookFor, K } from "/src/bridge/web/static/js/pixel/office.js";

export { person, lookFor, K };

export const W = 320, H = 180, SCALE = 4;
export const DUR = parseFloat(new URLSearchParams(location.search).get("d") || "10");

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, u) => a + (b - a) * u;
/** Progress 0..1 of time t between a and b (clamped). */
export const seg = (t, a, b) => clamp((t - a) / (b - a));
export const ease = {
  inOut: (u) => (u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2),
  out: (u) => 1 - Math.pow(1 - u, 3),
  in: (u) => u * u * u,
  back: (u) => { const c = 1.70158; return 1 + (c + 1) * Math.pow(u - 1, 3) + c * Math.pow(u - 1, 2); },
  bounce: (u) => { const n = 7.5625, d = 2.75; if (u < 1 / d) return n * u * u; if (u < 2 / d) return n * (u -= 1.5 / d) * u + 0.75; if (u < 2.5 / d) return n * (u -= 2.25 / d) * u + 0.9375; return n * (u -= 2.625 / d) * u + 0.984375; }
};
export const arc = (a, b, u, lift) => ({ x: lerp(a[0], b[0], u), y: lerp(a[1], b[1], u) - Math.sin(u * Math.PI) * lift });

/* ---------- the stage ---------- */
export function stage({ background = "grass" } = {}) {
  document.body.style.cssText = "margin:0;width:1280px;height:720px;overflow:hidden;background:#D4EAB0;font-family:Inter,system-ui,sans-serif;color:#1A1320";
  const root = document.createElement("div");
  root.style.cssText = "position:relative;width:1280px;height:720px;overflow:hidden";
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  cv.style.cssText = `position:absolute;left:0;top:0;width:${W * SCALE}px;height:${H * SCALE}px;image-rendering:pixelated`;
  const text = document.createElement("div");
  text.style.cssText = "position:absolute;inset:0;pointer-events:none";
  root.append(cv, text);
  document.body.append(root);
  const c = cv.getContext("2d");
  c.imageSmoothingEnabled = false;
  return { c, text, root, bg: background };
}

/** A text label on top of the picture. (x, y) are in pixel-world units; size in screen px. */
export function label(parent, html, { x, y, size = 22, font = "ui", color = K.ink, weight = 700, align = "left", w, opacity = 1, bg, pad = 0, border, shadow, rotate = 0, lh }) {
  const d = document.createElement("div");
  d.innerHTML = html;
  d.style.cssText = [
    "position:absolute", `left:${x * SCALE}px`, `top:${y * SCALE}px`, `font-size:${size}px`, `font-weight:${weight}`, `color:${color}`, `opacity:${opacity}`,
    `font-family:${font === "pixel" ? '"Press Start 2P",monospace' : "Inter,system-ui,sans-serif"}`, `text-align:${align}`, w ? `width:${w * SCALE}px` : "white-space:nowrap",
    bg ? `background:${bg}` : "", pad ? `padding:${pad}px` : "", border ? `border:3px solid ${K.ink}` : "", shadow ? "box-shadow:5px 5px 0 rgba(26,19,32,.22)" : "",
    rotate ? `transform:rotate(${rotate}deg)` : "", `line-height:${lh || 1.35}`, "will-change:transform,opacity"
  ].filter(Boolean).join(";");
  parent.append(d);
  return d;
}
export function setPos(el, x, y, opacity = 1, extra = "") {
  el.style.left = x * SCALE + "px"; el.style.top = y * SCALE + "px"; el.style.opacity = opacity; el.style.transform = extra;
}

/* ---------- pixel drawing ---------- */
export const px = (c, x, y, w, h, col) => { c.fillStyle = col; c.fillRect(Math.round(x), Math.round(y), w, h); };
export const box = (c, x, y, w, h, fill, line = K.ink) => { px(c, x - 1, y - 1, w + 2, h + 2, line); px(c, x, y, w, h, fill); };

export function background(c, t = 0) {
  px(c, 0, 0, W, H, "#D4EAB0");
  for (let y = 0; y < H; y += 8) for (let x = (y / 8) % 2 ? 0 : 8; x < W; x += 16) px(c, x, y, 8, 8, "#CDE5A8");
}

export function panel(c, x, y, w, h, fill = K.cream100) {
  px(c, x + 2, y + 2, w, h, "rgba(26,19,32,.18)");
  box(c, x, y, w, h, fill);
}

/** A laptop: open lid with a screen you can fill, on a base. Returns the screen rectangle. */
export function laptop(c, x, y, w = 70, h = 46, screen = K.cream50) {
  box(c, x, y, w, h, K.ink700);
  px(c, x + 3, y + 3, w - 6, h - 6, screen);
  box(c, x - 6, y + h + 2, w + 12, 5, K.cream300);
  px(c, x + w / 2 - 8, y + h + 4, 16, 1, K.ink500);
  return { x: x + 3, y: y + 3, w: w - 6, h: h - 6 };
}

export function folder(c, x, y, col = K.lemon) { box(c, x - 4, y - 3, 9, 7, col); px(c, x - 4, y - 5, 4, 2, col); px(c, x - 4, y - 5, 4, 1, K.ink); }
export function paper(c, x, y, col = K.cream50) { box(c, x - 3, y - 4, 7, 8, col); px(c, x - 2, y - 2, 5, 1, K.ink300); px(c, x - 2, y, 5, 1, K.ink300); px(c, x - 2, y + 2, 3, 1, K.ink300); }
export function coin(c, x, y, mark = false) { box(c, x - 3, y - 3, 6, 6, K.lemon); px(c, x - 2, y - 2, 1, 1, K.cream50); if (mark) { px(c, x - 1, y - 2, 2, 1, K.ink); px(c, x, y - 1, 1, 1, K.ink); px(c, x - 1, y, 1, 1, K.ink); px(c, x - 1, y + 2, 1, 1, K.ink); } }

export function lock(c, x, y, open = false, crack = 0, col = K.lemon) {
  const dx = crack ? Math.round(Math.sin(crack * 40) * 1) : 0;
  box(c, x - 5 + dx, y, 11, 8, col);
  px(c, x + dx, y + 3, 1, 3, K.ink);
  const top = open ? y - 7 : y - 5;
  px(c, x - 3, top, 1, 6, K.ink); px(c, x + 3, top, 1, 6, K.ink); px(c, x - 3, top, 7, 1, K.ink);
  if (crack > 0.5) { px(c, x - 1, y + 1, 1, 3, K.coral); px(c, x, y + 4, 1, 2, K.coral); px(c, x + 1, y + 6, 1, 2, K.coral); }
}

export function cloud(c, x, y, scale = 1, col = K.skyL, face = true, t = 0) {
  const s = (v) => Math.round(v * scale);
  const parts = [[-22, 4, 44, 14], [-14, -6, 26, 14], [2, -10, 22, 18], [-26, 8, 16, 10], [14, 6, 18, 12]];
  parts.forEach(([ox, oy, w, h]) => px(c, x + s(ox) - 1, y + s(oy) - 1, s(w) + 2, s(h) + 2, K.ink));
  parts.forEach(([ox, oy, w, h]) => px(c, x + s(ox), y + s(oy), s(w), s(h), col));
  if (face) {  // a blank visor: it has no face to trust
    box(c, x - s(11), y + s(2), s(24), s(8), K.ink700);
    const blink = Math.floor(t * 2) % 5 === 0;
    px(c, x - s(6), y + s(5), 3, blink ? 1 : 3, K.mint); px(c, x + s(5), y + s(5), 3, blink ? 1 : 3, K.mint);
  }
}

export function shelf(c, x, y, w, cols, lit = 1, glow = 0) {
  box(c, x, y, w, 11, lit ? K.cream50 : K.ink100);
  const n = Math.floor((w - 6) / 6);
  for (let i = 0; i < n; i++) px(c, x + 3 + i * 6, y + 2, 4, 7, lit ? cols[i % cols.length] : K.ink300);
  if (glow > 0) { c.globalAlpha = 0.35 * glow; px(c, x - 3, y - 3, w + 6, 17, K.lemon); c.globalAlpha = 1; box(c, x, y, w, 11, K.cream50); for (let i = 0; i < n; i++) px(c, x + 3 + i * 6, y + 2, 4, 7, cols[i % cols.length]); }
}

export function thumbDown(c, x, y) {   // a red cross in a box: "this went wrong"
  box(c, x - 7, y - 7, 14, 14, K.coralL);
  for (let i = 0; i < 8; i++) { px(c, x - 4 + i, y - 4 + i, 2, 2, K.coral); px(c, x + 3 - i, y - 4 + i, 2, 2, K.coral); }
}

export function mask(c, x, y) { box(c, x - 6, y - 3, 13, 6, K.ink); px(c, x - 4, y - 1, 3, 1, K.cream50); px(c, x + 2, y - 1, 3, 1, K.cream50); }
export function siren(c, x, y, on) { box(c, x - 3, y - 5, 7, 6, on ? K.coral : K.coralL); px(c, x - 4, y + 1, 9, 2, K.ink); }

export function glassRoom(c, x, y, w, h, alpha = 1) {
  c.globalAlpha = alpha;
  px(c, x - 1, y - 1, w + 2, h + 2, K.ink);
  px(c, x, y, w, h, K.skyL);
  for (let i = 0; i < 4; i++) px(c, x + 6 + i * 14, y + 2, 1, 5, "#FFFFFF");
  c.globalAlpha = 1;
}

export const AGENT = { shirt: K.lilac, hat: "wizard", skin: "#E0AC82", hair: K.ink };
export const ME = { shirt: K.mint, hat: "cap", skin: "#E0AC82", hair: K.ink };
export const GUARD = { shirt: K.ink700, hat: "guard", skin: "#E0AC82", hair: K.ink };

/** Fade a whole frame in or out (used for scene start and end). */
export function fade(c, u) { if (u >= 1) return; c.globalAlpha = 1 - u; px(c, 0, 0, W, H, K.cream100); c.globalAlpha = 1; }

export function fontFace() {
  const s = document.createElement("style");
  s.textContent = `@font-face{font-family:"Press Start 2P";src:url("/src/bridge/web/static/fonts/press-start-2p-latin-400.woff2") format("woff2")}
@font-face{font-family:"Inter";font-weight:100 900;src:url("/src/bridge/web/static/fonts/inter-latin-var.woff2") format("woff2")}`;
  document.head.append(s);
}
