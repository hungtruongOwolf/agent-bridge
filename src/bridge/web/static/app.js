/* Agent Bridge console: start-up, the shared helpers every screen uses, and the front door (type or say what you need).
   Plain language throughout. Every string from the server is inserted with textContent, never as markup. */
(function () {
  "use strict";
  const TOKEN = document.body.dataset.token;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const BAD = new Proxy({}, { get: (_, k) => (S && S.blocked_phrases && S.blocked_phrases[k]) || undefined });  // one wording, kept on the server
  let S = null, voiceOn = false, recognition = null;

  window.niceName = (id) => String(id || "").split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  const cents = (c) => c + "¢";

  const KNOWN = /spending limit|still working|write a message|characters|full|exist|no longer|shelf|shelves|type|text|secret|everyday|name|hold is not approved|payment could not|not helpful|already|limit|remember|choose|file|levels|add between/i;
  function friendly(msg, status) {
    if (msg && KNOWN.test(msg) && !/digest|registered|revoked|run_id|under that id|Error/.test(msg)) return msg;
    if (status === 403) return "This page lost its permission to talk to the console. Reload the page.";
    if (status === 503) return "The payment service has not answered yet. Try again in a moment.";
    return "Something went wrong. Please try again.";
  }

  async function api(path, body) {
    const r = await fetch(path, body ? { method: "POST", headers: { "X-Bridge-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const j = await r.json();
    if (!r.ok) throw new Error(friendly(j.error, r.status));
    return j;
  }

  function drawCoins() {
    const w = S.payments; if (!w) return;
    $("coinchip").textContent = "Paid to helpers " + cents(w.paid_out) + ", on hold " + cents(w.held);
    $("coinlabel").textContent = w.provider === "paypal-sandbox" ? "PayPal coins" : "Coins";
  }

  async function refresh() {
    S = await api("/api/state"); drawCoins();
    ["Market", "MemoryUI", "ChatUI"].forEach((n) => { if (window[n] && window[n].redraw) window[n].redraw(); });
  }

  /* ---------- the front door ---------- */
  /* Say what you need, and the helpers whose own skills fit are suggested. Nothing starts or spends by itself: the
     suggestion only opens a chat with your question typed in, and you press Send yourself. */
  async function ask(text, spoken) {
    text = text.trim(); if (!text) return;
    const box = $("recs"); box.replaceChildren(el("p", "small muted", "Looking for the right helper…"));
    let found;
    try { found = (await api("/api/match?q=" + encodeURIComponent(text.slice(0, 300)))).matches; } catch (e) { box.replaceChildren(el("p", "small", e.message)); return; }
    box.replaceChildren();
    if (!found.length) { box.append(el("p", "small", "Nobody is for hire yet.")); return; }
    box.append(el("p", "recshead", found[0].matched ? "These helpers fit what you asked:" : "Nobody says they are made for that. The best tested helpers are:"));
    found.forEach((m) => {
      const row = el("div", "rec"), who = el("div", "who");
      who.append(el("span", "name", window.niceName(m.id)), el("span", "blurb", m.reason + (m.trust != null ? " Trust " + m.trust + " out of 100." : " Not tested yet.")));
      const go = el("button", "btn go2", "Chat about this, " + cents(m.price_cents) + " an answer"); go.type = "button";
      go.onclick = async () => { box.replaceChildren(); $("ask").value = ""; await window.ChatUI.startWith(m.key, text); };
      const meet = el("button", "btn", "Meet"); meet.type = "button"; meet.onclick = () => window.ChatUI.profile(m.key);
      row.append(who, go, meet); box.append(row);
    });
    const dismiss = el("button", "linkbtn", "Close"); dismiss.type = "button"; dismiss.onclick = () => box.replaceChildren(); box.append(dismiss);
    const first = found[0];
    const line = (first.matched ? "I would try " : "The best tested helper is ") + window.niceName(first.id) + ". " + first.reason + " Nothing starts until you press Send.";
    if (spoken && "speechSynthesis" in window) { try { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(line)); } catch (e) { /* speaking is optional */ } }
  }
  function assistantSay(text) { $("recs").replaceChildren(el("p", "small", text)); }
  function setupVoice() {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $("mic");
    if (!Rec) { mic.hidden = true; return; }
    recognition = new Rec(); recognition.lang = "en-US"; recognition.interimResults = false;
    recognition.onresult = (e) => { const t = e.results[0][0].transcript; $("ask").value = t; voiceOn = true; ask(t, true); };
    recognition.onend = () => { mic.classList.remove("on"); mic.setAttribute("aria-pressed", "false"); };
    recognition.onerror = () => { mic.classList.remove("on"); assistantSay("I could not hear you. You can type instead."); };
    mic.onclick = () => { try { recognition.start(); mic.classList.add("on"); mic.setAttribute("aria-pressed", "true"); } catch (e) { /* already listening */ } };
  }

  /* ---------- start up ---------- */
  async function init() {
    try {
      S = await api("/api/state");
      drawCoins();
      $("askform").onsubmit = (e) => { e.preventDefault(); voiceOn = false; ask($("ask").value, false); $("ask").select(); };
      setupVoice();
      $("helpbtn").onclick = () => $("help").showModal(); $("helpclose").onclick = () => $("help").close();
      window.Bridge = { api, el, state: () => S, refresh, cents, niceName: window.niceName, blocked: S.blocked_phrases, bad: BAD };
      window.Market.mount(window.Bridge); window.MemoryUI.mount(window.Bridge); window.Studio.mount(window.Bridge); window.ChatUI.mount(window.Bridge);
      const logo = $("logo"), c = logo.getContext("2d"); c.imageSmoothingEnabled = false; c.fillStyle = "#FFF8E7"; c.fillRect(0, 0, 20, 14);
      window.OfficeArt.person(c, 10, 14, { pose: "idle", facing: "f", shirt: "#5CA97A", hat: "cap", skin: "#E0AC82", hair: "#1A1320" }, 0);
    } catch (e) {
      $("stalls").replaceChildren(el("p", "empty", "The console could not load: " + e.message + " Reload this page in a moment."));
    }
  }
  init();
})();
