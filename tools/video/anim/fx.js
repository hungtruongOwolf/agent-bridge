/* Effects for the animation scenes, on top of lib.js. Everything is a pure function of time t (seconds): no timers, no real clock, no Math.random.

   sentenceTimes(vo, DUR)   when each sentence of the voice-over starts and ends inside a scene of length DUR (voice starts LEAD in, ends TAIL before the end)
   spring(u)                 0 -> 1 with a little overshoot and settle (u = 0..1 progress)
   Camera                    pan and zoom the pixel world: cam.at(t) gives {x,y,zoom}; cam.apply(c, t) wraps drawing between save/restore
   burst / sparks            deterministic particle bursts
   Words                     text that arrives word by word (blur + rise + overshoot), driven by seek
   glow, vignette, grain     finishing touches
*/
import { W, H, SCALE, clamp, lerp, seg, ease, px, K } from "./lib.js";

export const LEAD = 0.5, TAIL = 0.6;   // must match edit.py

/** Sentence start/end times (seconds from the scene start), spread over the voice by characters, like the subtitle file does. */
export function sentenceTimes(vo, DUR) {
  const text = vo.replace(/\s+/g, " ").trim();
  const sents = text.split(/(?<=[.?!])\s+/).filter(Boolean);
  const total = sents.reduce((a, s) => a + s.length, 0);
  const voice = DUR - LEAD - TAIL;
  let at = LEAD;
  return sents.map((s) => { const span = voice * s.length / total; const r = { text: s, a: at, b: at + span }; at += span; return r; });
}

/** Seeded random, so a frame is always the same. */
export function rng(seed) {
  let s = (seed * 2654435761) >>> 0;
  return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return (s >>> 0) / 4294967296; };
}

/** Under-damped spring from 0 to 1: quick, overshoots a little, settles. */
export function spring(u, k = 9, d = 0.55) {
  u = clamp(u);
  if (u <= 0) return 0;
  if (u >= 1) return 1;
  return 1 - Math.exp(-d * k * u) * Math.cos(k * u * 0.9);
}
export const smooth = (u) => u * u * (3 - 2 * u);
export const out5 = (u) => 1 - Math.pow(1 - clamp(u), 5);
export const inOut5 = (u) => (u < 0.5 ? 16 * u ** 5 : 1 - Math.pow(-2 * u + 2, 5) / 2);

/** A camera that follows keyframes: [{t, x, y, zoom}, ...]; moves between them with an ease. x,y are pixel-world coordinates of the view centre. */
export class Camera {
  constructor(keys) { this.keys = keys.slice().sort((a, b) => a.t - b.t); }
  at(t) {
    const k = this.keys;
    if (t <= k[0].t) return { x: k[0].x, y: k[0].y, zoom: k[0].zoom };
    for (let i = 1; i < k.length; i++) {
      if (t <= k[i].t) {
        const u = inOut5(seg(t, k[i - 1].t, k[i].t)), a = k[i - 1], b = k[i];
        return { x: lerp(a.x, b.x, u), y: lerp(a.y, b.y, u), zoom: lerp(a.zoom, b.zoom, u) };
      }
    }
    const l = k[k.length - 1];
    return { x: l.x, y: l.y, zoom: l.zoom };
  }
  /** Draw the world through the camera. `world()` draws in the 320 x 180 pixel space. A slow drift keeps still moments alive. */
  apply(c, t, world, shake = 0) {
    const p = this.at(t);
    const dx = Math.sin(t * 0.7) * 0.6 + (shake ? Math.sin(t * 90) * shake : 0), dy = Math.cos(t * 0.5) * 0.4 + (shake ? Math.cos(t * 83) * shake : 0);
    c.save();
    c.translate(W / 2, H / 2);
    c.scale(p.zoom, p.zoom);
    c.translate(-p.x + dx, -p.y + dy);
    world(p);
    c.restore();
    return p;
  }
  /** Convert a pixel-world point to screen CSS pixels (to place text labels that follow the camera). */
  toScreen(t, x, y) {
    const p = this.at(t);
    return { x: ((x - p.x) * p.zoom + W / 2) * SCALE, y: ((y - p.y) * p.zoom + H / 2) * SCALE, s: p.zoom };
  }
}

/** A burst of square sparks from (x, y) starting at t0. Draws in pixel-world units. */
export function burst(c, t, t0, x, y, { n = 18, colors = [K.lemon, K.coral, K.mint, K.sky], speed = 38, life = 0.9, size = 2, gravity = 40, seed = 1 } = {}) {
  const u = (t - t0) / life;
  if (u < 0 || u > 1) return;
  const r = rng(seed);
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2, v = speed * (0.4 + r() * 0.8), col = colors[i % colors.length];
    const px_ = x + Math.cos(a) * v * u * life, py_ = y + Math.sin(a) * v * u * life + 0.5 * gravity * (u * life) ** 2;
    c.globalAlpha = 1 - u * u;
    px(c, px_, py_, size, size, col);
  }
  c.globalAlpha = 1;
}

/** A line of small dots flowing from a to b (data moving). phase 0..1 loops. */
export function flow(c, t, a, b, { dots = 8, speed = 0.7, col = K.sky, size = 2, arcLift = 0 } = {}) {
  for (let i = 0; i < dots; i++) {
    const u = (t * speed + i / dots) % 1;
    const x = lerp(a[0], b[0], u), y = lerp(a[1], b[1], u) - Math.sin(u * Math.PI) * arcLift;
    c.globalAlpha = Math.sin(u * Math.PI);
    px(c, x, y, size, size, col);
  }
  c.globalAlpha = 1;
}

/** Text that arrives word by word. `words` = html string; each word rises, un-blurs and settles with a small overshoot.
    update(t) places it; call every frame. Options: x,y in pixel-world units, size px, w width (world units), at (start second), gap (stagger). */
export function Words(parent, html, { x = 0, y = 0, size = 40, w = 300, at = 0, gap = 0.09, color = K.ink, weight = 800, align = "left", font = "ui", leave = null, shadow = true } = {}) {
  const wrap = document.createElement("div");
  wrap.style.cssText = `position:absolute;left:${x * SCALE}px;top:${y * SCALE}px;width:${w * SCALE}px;font-size:${size}px;font-weight:${weight};color:${color};text-align:${align};line-height:1.22;` +
    `font-family:${font === "pixel" ? '"Press Start 2P",monospace' : "Inter,system-ui,sans-serif"};${shadow ? "text-shadow:3px 3px 0 rgba(26,19,32,.14);" : ""}letter-spacing:-0.01em`;
  const spans = [];
  html.split(/(\s+)/).forEach((tok) => {
    if (!tok.trim()) { wrap.append(document.createTextNode(" ")); return; }
    const s = document.createElement("span");
    s.innerHTML = tok;
    s.style.cssText = "display:inline-block;will-change:transform,opacity,filter";
    wrap.append(s); spans.push(s);
  });
  parent.append(wrap);
  return {
    el: wrap,
    update(t) {
      const out = leave ? seg(t, leave, leave + 0.35) : 0;
      spans.forEach((s, i) => {
        const u = seg(t, at + i * gap, at + i * gap + 0.45), e = spring(u, 8, 0.6);
        s.style.opacity = Math.min(out < 1 ? 1 : 0, clamp(u * 2.2)) * (1 - out);
        s.style.transform = `translateY(${(1 - e) * 22}px) scale(${0.9 + 0.1 * e})`;
        s.style.filter = `blur(${(1 - clamp(u * 1.6)) * 6}px)`;
      });
    },
  };
}

/** Soft coloured glow behind something at (x, y) in pixel-world units. */
export function glow(c, x, y, r, col = K.lemon, a = 0.5) {
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, col); g.addColorStop(1, "rgba(255,255,255,0)");
  c.globalAlpha = a; c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2); c.globalAlpha = 1;
}

/** Darkened corners, for depth. */
export function vignette(c, a = 0.22) {
  const g = c.createRadialGradient(W / 2, H / 2, H * 0.55, W / 2, H / 2, H * 1.05);
  g.addColorStop(0, "rgba(26,19,32,0)"); g.addColorStop(1, `rgba(26,19,32,${a})`);
  c.fillStyle = g; c.fillRect(0, 0, W, H);
}

/** Wipe the frame in from a side (scene transitions happen in the edit; this is for reveals inside a scene). */
export function reveal(c, u, col = K.ink) {
  if (u >= 1) return;
  c.fillStyle = col; c.fillRect(0, 0, W * (1 - ease.inOut(u)), H);
}

/** A horizontal bar that grows to value/max with a number counting up (for scores). */
export function bar(c, x, y, w, h, value, max, u, col, back = K.cream300) {
  px(c, x - 1, y - 1, w + 2, h + 2, K.ink); px(c, x, y, w, h, back);
  px(c, x, y, Math.round(w * (value / max) * out5(u)), h, col);
}
