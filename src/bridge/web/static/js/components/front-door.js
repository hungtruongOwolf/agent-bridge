/* The front door: say what you need (typed or spoken) and the helpers whose own skills fit are suggested. Nothing starts or
   spends by itself: a suggestion only opens a chat with the question typed in, and the person presses Send. */
import { $, el, btn, link } from "../lib/dom.js";
import { get, url } from "../lib/api.js";
import { niceName } from "../lib/format.js";
import { paths } from "../lib/nav.js";
import { startChat } from "../lib/chats.js";

let recognition = null;

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  try { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } catch (e) { /* speaking is optional */ }
}

async function ask(text, spoken) {
  text = text.trim();
  if (!text) return;
  const box = $("recs");
  box.replaceChildren(el("p", "small muted", "Looking for the right helper…"));
  let found;
  try { found = (await get(url("/api/match", { q: text.slice(0, 300) }))).matches; } catch (e) { box.replaceChildren(el("p", "small", e.message)); return; }
  box.replaceChildren();
  if (!found.length) { box.append(el("p", "small", "Nobody is for hire yet.")); return; }
  if (found[0].matched) found = found.filter((m) => m.matched);  // only the ones that really fit, when there are any
  box.append(el("p", "recshead", found[0].matched ? "These helpers fit what you asked:" : "Nobody says they are made for that. The best tested helpers are:"));
  found.forEach((m) => {
    const row = el("div", "rec"), who = el("div", "who");
    who.append(el("span", "name", niceName(m.id)), el("span", "blurb", m.reason + (m.trust != null ? ` Trust ${m.trust} out of 100.` : " Not tested yet.")), el("span", "blurb", `Price: ${m.price_text}.`));
    row.append(who, btn("Chat about this", "btn go2", () => { box.replaceChildren(); $("ask").value = ""; startChat(m.key, text); }), link(paths.helper(m.key), "Meet", "btn"));
    box.append(row);
  });
  box.append(btn("Close", "linkbtn", () => box.replaceChildren()));
  if (spoken) speak((found[0].matched ? "I would try " : "The best tested helper is ") + niceName(found[0].id) + ". " + found[0].reason + " Nothing starts until you press Send.");
}

function setupVoice() {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $("mic");
  if (!Rec) { mic.hidden = true; return; }
  recognition = new Rec();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.onresult = (e) => { const t = e.results[0][0].transcript; $("ask").value = t; ask(t, true); };
  recognition.onend = () => { mic.classList.remove("on"); mic.setAttribute("aria-pressed", "false"); };
  recognition.onerror = () => { mic.classList.remove("on"); $("recs").replaceChildren(el("p", "small", "I could not hear you. You can type instead.")); };
  mic.onclick = () => { try { recognition.start(); mic.classList.add("on"); mic.setAttribute("aria-pressed", "true"); } catch (e) { /* already listening */ } };
}

export function setupFrontDoor() {
  $("askform").onsubmit = (e) => { e.preventDefault(); ask($("ask").value, false); $("ask").select(); };
  setupVoice();
}
