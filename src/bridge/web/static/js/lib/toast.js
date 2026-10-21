/* A short message that appears where you are looking, whatever screen you are on. */
import { $, el } from "./dom.js";

let timer = null;

/** toast("Saved."), toast("Could not save", true), toast("Moved to the trash.", false, {label: "Undo", fn}) */
export function toast(text, bad, action) {
  let t = $("toast");
  if (!t) {
    t = el("div");
    t.id = "toast";
    t.setAttribute("role", "status");
    t.setAttribute("aria-live", "polite");
    document.body.append(t);
  }
  t.replaceChildren(el("span", null, text || ""));
  if (text && action) {
    const b = el("button", "toastbtn", action.label);
    b.type = "button";
    b.onclick = () => { t.className = ""; action.fn(); };
    t.append(b);
  }
  t.className = text ? (bad ? "bad on" : "on") : "";
  clearTimeout(timer);
  if (text) timer = setTimeout(() => { t.className = ""; }, action ? 9000 : bad ? 6000 : 3500);
}

/** The message for a changed-memory style result: errors are red, everything else is calm. */
export const say = (text) => toast(text, !/^(Saved|Moved)/.test(text));
