/* The replay: stands in for the console's server so the real front end runs without one.

   It replaces window.fetch for /api/* and answers from fixtures/replay.json, a recording of a real run on the practice PayPal server.
   It is a small state machine, not a list of canned replies. The state is a "phase" kept in localStorage (so a reload, or the approval
   page in another tab, sees the same story):

     0 start   1 chat created   2 shelf ticked   3 first question asked: hold to approve   4 first answer
     5 second question asked: hold to approve   6 second answer   7 second answer marked "not helpful"

   Anything the recording does not cover gets a plain sentence, never an error screen. Nothing here uses the network except
   same-origin static files. */
(() => {
  const KEY = "agent-bridge-replay";
  const LIMIT = "This replay covers the Account Brief flow only. To try your own files and everything else, run agent-bridge locally.";
  const QUESTIONS = ["Which accounts are at risk?", "And which one is the biggest?"];
  const realFetch = window.fetch.bind(window);

  /* ---------- state ---------- */
  const fresh = () => ({ phase: 0, shelves: [], approved: {} });
  const load = () => { try { return Object.assign(fresh(), JSON.parse(localStorage.getItem(KEY) || "{}")); } catch (e) { return fresh(); } };
  const save = (s) => { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private window: the replay still works in this tab */ memory = s; } };
  let memory = null;
  const state = () => memory || load();
  const update = (fn) => { const s = state(); fn(s); save(s); window.dispatchEvent(new Event("replay-phase")); return s; };

  /* ---------- the recording ---------- */
  let R = null;
  const ready = realFetch("/fixtures/replay.json").then((r) => r.json()).then((j) => { R = j; });
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const snap = (path, phase) => {
    const by = R.snaps[path];
    if (!by) return null;
    const ks = Object.keys(by).map(Number).sort((a, b) => a - b);
    let pick = ks[0];
    for (const k of ks) if (k <= phase) pick = k;
    return clone(by[pick]);
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  class Say extends Error { constructor(msg, status = 400) { super(msg); this.status = status; } }
  const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  /* ---------- helpers for the pieces that depend on what you ticked ---------- */
  const within = (path, sel) => path === sel || path.startsWith(sel + "/");
  const secret = (n) => n.sensitivity === "high";

  function threadView(s) {
    const t = snap("/api/thread", s.phase);
    if (!t) throw new Say("That chat does not exist in this replay. Go back to the office.", 404);
    if (s.phase >= 2 && s.shelves) t.lens = Object.assign({}, t.lens, { shelves: s.shelves });
    return t;
  }

  function context(s) {
    const c = snap("/api/thread/context", Math.max(s.phase, 1));
    if (!c) throw new Say("That chat does not exist in this replay. Go back to the office.", 404);
    const sel = s.shelves || [];
    c.shelves.forEach((sh) => {
      sh.state = sel.some((x) => within(sh.path, x)) ? "open" : sel.some((x) => within(x, sh.path)) ? "partly" : "closed";
    });
    const notes = R.memory.items.filter((n) => sel.some((x) => within(n.shelf, x)));
    const open = notes.filter((n) => !secret(n));
    c.shared_count = open.length;
    const shape = Object.keys((snap("/api/thread/context", 2).shared || [{}])[0] || {});
    c.shared = open.slice(0, 3).map((n) => Object.fromEntries(shape.map((k) => [k, n[k]])));
    c.shared_more = Math.max(0, open.length - 3);
    c.held_back = notes.filter(secret).slice(0, 3).map((n) => Object.fromEntries(shape.map((k) => [k, n[k]])));
    return c;
  }

  function notes(q) {
    let items = R.memory.items;
    const ids = (q.get("ids") || "").split(",").filter(Boolean);
    if (ids.length) items = ids.map((id) => items.find((n) => n.id === id)).filter(Boolean);
    const shelf = q.get("shelf");
    if (shelf) items = items.filter((n) => within(n.shelf, shelf));
    const text = (q.get("q") || "").toLowerCase();
    if (text) items = items.filter((n) => (n.text + " " + (n.title || "") + " " + n.shelf_name).toLowerCase().includes(text));
    const off = parseInt(q.get("offset") || "0", 10), lim = parseInt(q.get("limit") || "30", 10);
    return { items: clone(items.slice(off, off + lim)) };
  }

  const keyFor = (path, q) => path + (q.toString() ? "?" + [...q.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => k + "=" + v).join("&") : "");

  /* ---------- the routes ---------- */
  async function get(path, q) {
    const s = state();
    if (path === "/api/state" || path === "/api/office" || path === "/api/payments") return snap(path, s.phase);
    if (path === "/api/threads") {
      if (s.phase < 1) return { threads: [] };
      const t = threadView(s), last = (t.messages[t.messages.length - 1] || {}).text || "";
      return { threads: [{ id: t.id, title: t.title, agent_key: t.agent.key, updated: Date.now() / 1000, messages: t.messages.length, last: last.slice(0, 80) }] };
    }
    if (path === "/api/thread") return threadView(s);
    if (path === "/api/thread/context") return context(s);
    if (path === "/api/thread/progress") return { steps: [] };
    if (path === "/api/memory") return notes(q);
    const hit = R.statics[keyFor(path, q)] || (path === "/api/how" ? null : R.statics[path]);
    if (hit) return clone(hit);
    throw new Say(LIMIT);
  }

  async function post(path, body) {
    const s = state();
    if (path === "/api/threads") {
      if (s.phase < 1) update((x) => { x.phase = 1; });
      return threadView(state());
    }
    if (path === "/api/thread/settings") {
      if (Array.isArray(body.shelves)) update((x) => { x.shelves = body.shelves; if (x.phase === 1 && body.shelves.length) x.phase = 2; else if (x.phase === 2 && !body.shelves.length) x.phase = 1; });
      return threadView(state());
    }
    if (path === "/api/thread/send") {
      if (s.phase < 1) throw new Say("Open a chat with a helper first.");
      await sleep(500);
      if (s.phase === 1 || s.phase === 2) { update((x) => { x.phase = 3; }); return withShelves(R.posts.send1, state()); }
      if (s.phase === 3) return withShelves(R.posts.send1, s);
      if (s.phase === 4) { update((x) => { x.phase = 5; }); return withShelves(R.posts.send2, state()); }
      if (s.phase === 5) return withShelves(R.posts.send2, s);
      throw new Say("The replay ends here: " + LIMIT);
    }
    if (path === "/api/run/continue") {
      const first = body.run_id === R.posts.send1.run_id, second = body.run_id === R.posts.send2.run_id;
      if (!first && !second) throw new Say("That run is not part of this replay.");
      if (first ? s.phase >= 4 : s.phase >= 6) return clone(first ? R.posts.cont1 : R.posts.cont2);
      if (!s.approved[body.run_id]) throw new Say("The hold is not approved yet. Open the approval page and press Approve the hold.", 402);
      await sleep(2600);                                                // the real run takes a while: the helper reads, thinks, checks
      update((x) => { x.phase = first ? 4 : 6; });
      return clone(first ? R.posts.cont1 : R.posts.cont2);
    }
    if (path === "/api/thread/cancel") {
      update((x) => { if (x.phase === 3) x.phase = x.shelves.length ? 2 : 1; else if (x.phase === 5) x.phase = 4; delete x.approved[body.run_id]; });
      return {};
    }
    if (path === "/api/thread/reject") {
      if (s.phase !== 6) throw new Say("This answer is already settled in this replay.");
      update((x) => { x.phase = 7; });
      return clone(R.posts.reject);
    }
    throw new Say(LIMIT);
  }

  function withShelves(j, s) {
    const r = clone(j);
    if (r.thread && r.thread.lens) r.thread.lens.shelves = s.shelves;
    if (r.approve_url && r.approve_url.startsWith("/")) r.approve_url = location.origin + r.approve_url;   // the console only shows the link for a full address
    return r;
  }

  async function api(input, init) {
    await ready;
    const u = new URL(typeof input === "string" ? input : input.url, location.origin);
    const method = ((init && init.method) || (typeof input !== "string" && input.method) || "GET").toUpperCase();
    try {
      if (method === "GET") return json(await get(u.pathname, u.searchParams));
      let body = {};
      try { body = JSON.parse((init && init.body) || "{}"); } catch (e) { /* no body */ }
      return json(await post(u.pathname, body));
    } catch (e) {
      if (e instanceof Say) return json({ error: e.message }, e.status);
      console.warn("replay:", e);
      return json({ error: LIMIT }, 400);
    }
  }

  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const path = new URL(url, location.origin).pathname;
    if (new URL(url, location.origin).origin === location.origin && path.startsWith("/api/")) return api(input, init);
    if (new URL(url, location.origin).origin !== location.origin) return Promise.reject(new TypeError("replay: no network"));
    return realFetch(input, init);
  };

  /* ---------- the note, the hint and "start over" ---------- */
  const HINTS = [
    "Pick Account Brief to open a chat with it.",
    "Open “What the helper sees” and tick Work › Accounts › Initech.",
    "Ask the question below. The helper will ask for a hold first.",
    "Press “Open the approval page”, then “Approve the hold”. This chat carries on by itself.",
    "Click the coins chip to read the receipt. Asking again accepts this answer.",
    "Approve the second hold the same way.",
    "Press “Not helpful” under the answer, then open the coins chip again.",
    "That is the whole flow. Look around, or start over.",
  ];
  function bar() {
    const el = document.createElement("div");
    el.id = "replaybar";
    el.setAttribute("role", "note");
    el.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#1A1320;color:#FFF8E7;font:13px/1.35 Inter,system-ui,sans-serif;padding:7px 14px;display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center";
    const note = document.createElement("span");
    note.textContent = "Replay of a real run recorded on the practice PayPal server. Test money. Nothing here talks to PayPal or a model.";
    const hint = document.createElement("b"); hint.id = "replayhint"; hint.style.cssText = "color:#F3E4BC";
    const fill = document.createElement("button"); fill.textContent = "Fill in the question"; fill.hidden = true;
    const again = document.createElement("button"); again.textContent = "Start over";
    [fill, again].forEach((b) => { b.type = "button"; b.style.cssText = "font:inherit;color:#1A1320;background:#F3E4BC;border:2px solid #F3E4BC;border-radius:3px;padding:1px 8px;cursor:pointer"; });
    fill.onclick = () => {
      const d = document.getElementById("draft");
      if (!d) return;
      d.value = QUESTIONS[state().phase >= 4 ? 1 : 0];
      d.dispatchEvent(new Event("input", { bubbles: true }));
      d.focus();
    };
    again.onclick = () => { save(fresh()); memory = null; location.assign("/"); };
    el.append(note, hint, fill, again);
    document.body.append(el);
    document.body.style.paddingBottom = "56px";
    const refresh = () => {
      const s = state();
      hint.textContent = HINTS[Math.min(s.phase, 7)];
      fill.hidden = !(s.phase === 2 || s.phase === 4) || !document.getElementById("draft");
    };
    refresh();
    setInterval(refresh, 300);
    window.addEventListener("storage", refresh);
    window.addEventListener("replay-phase", refresh);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bar); else bar();
})();
