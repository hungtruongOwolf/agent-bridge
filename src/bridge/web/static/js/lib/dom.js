/* Small DOM helpers shared by every screen. Text from the server is always inserted with textContent, never as markup. */

export const $ = (id) => document.getElementById(id);

export function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function btn(text, cls, fn) {
  const b = el("button", cls || "btn", text);
  b.type = "button";
  if (fn) b.onclick = fn;
  return b;
}

/** A link the router handles (no page load). `href` is an app path like "/chats/t_1". */
export function link(href, text, cls) {
  const a = el("a", cls, text);
  a.href = href;
  a.dataset.link = "";
  return a;
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function sv(tag, attrs, text) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  return e;
}

/** A button that asks twice: the first press changes its label, the second (within 4 s) does the thing. */
export function confirmTwice(b, label, fn) {
  if (b.dataset.armed) { fn(); return; }
  const old = b.textContent;
  b.dataset.armed = "1";
  b.textContent = label;
  setTimeout(() => { delete b.dataset.armed; b.textContent = old; }, 4000);
}

/** A labelled form field: <label><span>label</span> control <span>hint</span></label> */
export function field(label, control, hint) {
  const w = el("label", "fld");
  w.append(el("span", "small", label), control);
  if (hint) w.append(el("span", "small muted", hint));
  return w;
}

export function textInput(value, onInput, max) {
  const t = document.createElement("input");
  t.type = "text";
  t.value = value || "";
  t.maxLength = max || 200;
  t.oninput = () => onInput(t.value);
  return t;
}

export function textArea(value, rows, onInput, max) {
  const t = document.createElement("textarea");
  t.rows = rows;
  t.value = value || "";
  t.maxLength = max || 4000;
  t.oninput = () => onInput(t.value);
  return t;
}

export function numberInput(value, { step = 1, min, max, label }) {
  const e = document.createElement("input");
  e.type = "number";
  e.step = step;
  e.min = min;
  e.max = max;
  e.value = value;
  if (label) e.setAttribute("aria-label", label);
  return e;
}

/** Run `fn` at most once per `ms` after the last call. */
export function debounce(fn, ms) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
