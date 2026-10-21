/* The market floor: every chat is a small stall, and all of them are on one picture. A stall shows who you are talking
   with, what they are doing right now, and what they may see. Click a stall to walk in. Plain language; strings from the
   server are inserted with textContent only. */
(function () {
  "use strict";
  let B = null, timer = null, last = "", picking = false;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const btn = (text, cls, fn) => { const b = el("button", cls || "btn", text); b.type = "button"; if (fn) b.onclick = fn; return b; };
  const K = () => window.OfficeArt.K;
  const AWNINGS = ["coral", "mint", "sky", "lemon", "lilac", "peach"];
  const WHAT = { working: "Working", waiting: "Waiting for you", stopped: "Stopped by the guard", idle: "Answered", new: "Ready" };
  const sprites = new Set();  // every stall canvas currently on screen
  const WW = 56, WH = 40;

  function hash(s) { let h = 7; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return h; }

  /* ---------- a tiny office drawn on each stall ---------- */
  function px(c, x, y, w, h, col) { c.fillStyle = col; c.fillRect(Math.round(x), Math.round(y), w, h); }
  function box(c, x, y, w, h, fill) { px(c, x - 1, y - 1, w + 2, h + 2, K().ink); px(c, x, y, w, h, fill); }
  function paintStall(cv, t) {
    const c = cv.getContext("2d"), k = K(), st = cv._state || "new", agent = cv._agent || { id: "x", status: "certified" };
    c.imageSmoothingEnabled = false;
    px(c, 0, 0, WW, WH, k.cream200); px(c, 0, 31, WW, 9, k.wood); px(c, 0, 31, WW, 1, k.woodD);
    px(c, 3, 3, 10, 8, k.skyL); px(c, 3, 3, 10, 1, k.ink); px(c, 8, 3, 1, 8, k.ink);   // a window
    const look = window.OfficeArt.lookFor(agent.id, st === "stopped" ? "flagged" : agent.status);
    const beat = Math.floor(t / 320) % 2;
    const pose = st === "working" ? (beat ? "sit" : "up") : st === "stopped" ? "up" : "idle";
    // person first, the desk covers the legs
    window.OfficeArt.person(c, 20, st === "working" || st === "stopped" ? 30 : 31, Object.assign({ pose, facing: "f", mood: st === "stopped" ? "bad" : "ok" }, look), t);
    box(c, 6, 28, 34, 8, k.woodD); px(c, 6, 28, 34, 2, k.wood);
    // monitor
    box(c, 31, 18, 11, 9, k.ink700);
    px(c, 32, 19, 9, 6, st === "working" ? (beat ? k.mintL : k.skyL) : st === "stopped" ? k.coralL : k.skyL);
    if (st === "working") { px(c, 33, 21, 4 + beat * 2, 1, k.ink500); px(c, 33, 23, 6 - beat * 2, 1, k.ink500); }
    if (st === "waiting") {  // a coin bobs over the helper's head: it is waiting for your approval
      const y = 6 + (beat ? 1 : 0); box(c, 18, y, 5, 5, k.lemon); px(c, 19, y + 1, 1, 1, k.cream50);
    }
    if (st === "stopped") { const on = Math.floor(t / 220) % 2; box(c, 44, 22, 6, 6, on ? k.coral : k.coralL); px(c, 43, 28, 8, 2, k.ink); }
    if (st === "idle" && cv._answered) { box(c, 12, 25, 8, 4, k.cream50); px(c, 13, 26, 6, 1, k.ink300); }  // an answer lies on the desk
  }
  let raf = 0;
  function loop(ts) {
    sprites.forEach((cv) => { if (!cv.isConnected) sprites.delete(cv); else paintStall(cv, ts); });
    raf = sprites.size ? requestAnimationFrame(loop) : 0;
  }
  function watch(cv) { sprites.add(cv); if (!raf) raf = requestAnimationFrame(loop); }

  /* ---------- the floor ---------- */
  function chip(text, cls) { return el("span", "chip " + (cls || ""), text); }

  function bar(d) {
    const b = $("marketbar"); b.replaceChildren();
    const n = d.stalls.length;
    b.append(chip(n ? n + (n === 1 ? " chat open" : " chats open") + (d.working ? ", " + d.working + " working now" : "") : "No chats yet", d.working ? "busy" : ""));
    b.append(chip("Guard: " + (d.guard.stopped ? "stopped " + d.guard.stopped + " sneaky attempt" + (d.guard.stopped === 1 ? "" : "s") : "nothing suspicious so far"), d.guard.stopped ? "alarm" : "calm"));
    b.append(chip("Memory: " + d.memory.total + " files" + (d.memory.secret ? ", " + d.memory.secret + " secret stay home" : "")));
    b.append(btn(picking || !n ? "Hide the helpers" : "+ Open a new stall", "btn go2", () => { picking = !picking; $("hirepanel").hidden = !(picking || !n); drawPicker(); bar(d); }));
  }

  function stallCard(s) {
    const card = el("button", "stall state-" + s.state); card.type = "button";
    const col = AWNINGS[hash(s.agent.id) % AWNINGS.length];
    const awn = el("div", "awning"); awn.style.setProperty("--awn", "var(--" + col + ")");
    const cv = el("canvas"); cv.width = WW; cv.height = WH; cv._state = s.state; cv._agent = s.agent; cv._answered = s.messages > 1; cv.setAttribute("aria-hidden", "true");
    const top = el("div", "stop"); top.append(el("span", "lamp"), el("span", "swhat", WHAT[s.state] || s.state));
    card.append(awn, cv, top, el("div", "sname", s.title), el("div", "shelper", "with " + s.agent.name), el("div", "sline", s.line));
    const meta = el("div", "sbadges");
    meta.append(chip(s.shelf_count ? "Opens " + s.shelves.join(", ") + (s.shelf_count > s.shelves.length ? " +" + (s.shelf_count - s.shelves.length) : "") : "No shelves open", s.shelf_count ? "" : "calm"));
    meta.append(chip(B.cents(s.spent) + " spent" + (s.held ? ", " + B.cents(s.held) + " on hold" : "")));
    card.append(meta);
    card.setAttribute("aria-label", s.title + ", with " + s.agent.name + ". " + (WHAT[s.state] || "") + ". " + s.line);
    card.onclick = () => window.ChatUI.open(s.id);
    watch(cv);
    return card;
  }

  function draw(d) {
    bar(d);
    const box = $("stalls"); box.replaceChildren();
    d.stalls.forEach((s) => box.append(stallCard(s)));
    const add = el("button", "stall newstall"); add.type = "button";
    add.append(el("div", "plus", "+"), el("div", "sname", "Open a new stall"), el("div", "sline", "Pick a helper and start a conversation."));
    add.onclick = () => { picking = true; $("hirepanel").hidden = false; drawPicker(); $("hirepanel").scrollIntoView({ block: "nearest" }); };
    box.append(add);
    $("hirepanel").hidden = !(picking || !d.stalls.length);
  }

  async function poll() {
    if ($("view-office").hidden || document.hidden) return;
    try {
      const d = await B.api("/api/office");
      const sig = JSON.stringify(d);
      if (sig !== last) { last = sig; draw(d); }
    } catch (e) { /* the next poll tries again */ }
  }
  function start() { stop(); last = ""; drawPicker(); poll(); timer = setInterval(poll, 1500); }
  function stop() { clearInterval(timer); timer = null; }

  /* ---------- the people you can hire ---------- */
  function portrait(canvas, m) {
    const c = canvas.getContext("2d"); c.imageSmoothingEnabled = false; c.clearRect(0, 0, 22, 26);
    c.fillStyle = "#F4E9C7"; c.fillRect(0, 0, 22, 26);
    window.OfficeArt.person(c, 11, 25, Object.assign({ pose: "idle", facing: "f" }, window.OfficeArt.lookFor(m.id, m.status)), 0);
  }
  function pips(m) {
    const w = el("span", "pips" + (m.status === "certified" && m.score < 0.5 ? " warn" : ""));
    const n = m.status === "certified" ? Math.max(1, Math.round(m.score * 5)) : 0;
    for (let i = 0; i < 5; i++) w.append(el("i", i < n ? "on" : ""));
    return w;
  }
  function trustText(m) {
    if (m.status !== "certified") return "Not tested yet";
    const ev = /^(\d+)\/(\d+)/.exec(m.evidence || "");
    return "Trust " + Math.round(m.score * 100) + (ev ? ", passed " + ev[1] + " of " + ev[2] + " tests" : "");
  }
  function drawPicker() {
    const S = B.state(), box = $("picker"); box.replaceChildren();
    box.append(el("p", "small muted", "Pick who you want to talk with. Press “Meet” first to see what they can do and how they were tested."));
    const ok = S.market.filter((m) => m.status !== "flagged");
    if (!ok.length) box.append(el("p", "empty", "Nobody is available yet."));
    ok.forEach((m) => {
      const row = el("div", "pick"), cv = el("canvas"); cv.width = 22; cv.height = 26; cv.style.width = "44px"; cv.style.height = "52px"; portrait(cv, m);
      const who = el("div", "who"), nm = el("span", "name", B.niceName(m.id)); nm.append(el("span", "ver", " v" + m.version));
      who.append(nm, el("span", "blurb", m.summary));
      if ((m.skills || []).length) who.append(el("span", "blurb skills", m.skills.join(" · ")));
      const tr = el("div", "trust"); tr.append(pips(m), el("span", null, trustText(m)));
      if (m.status === "certified") tr.append(el("span", "tag good", "#" + m.rank));
      who.append(tr);
      const acts = el("div", "acts");
      acts.append(btn("Meet", "btn", () => window.ChatUI.profile(m.key)), btn("Chat, " + B.cents(Math.round(m.price_usd * 100)) + " per answer", "btn go2", () => window.ChatUI.startNew(m.key)));
      const fan = btn("♥ " + m.stars + " fans", "fan", async () => { try { const r = await B.api("/api/star", { key: m.key, user: "you" }); m.stars = r.stars; drawPicker(); } catch (e) { /* optional */ } });
      acts.append(fan);
      row.append(cv, who, acts); box.append(row);
    });
    const flagged = S.market.filter((m) => m.status === "flagged");
    if (flagged.length) {
      box.append(el("p", "small muted", flagged.length + " helper(s) were caught cheating while we tested them and cannot be chatted with:"));
      flagged.forEach((m) => {
        const reasons = [...new Set((m.violations || []).filter((v) => v !== "KILLED").map((v) => B.bad[v] || v))];
        box.append(el("p", "small", B.niceName(m.id) + " " + (reasons.length ? reasons.join(", and ") + "." : "was caught cheating.")));
      });
      box.append(el("p", "small muted", "To watch the guard work, open any chat and tick “Make the helper misbehave” under Demo tools."));
    }
  }

  function mount(bridge) { B = bridge; }
  window.Market = { mount, start, stop, redraw: () => { if (!$("view-office").hidden) { last = ""; poll(); drawPicker(); } }, drawPicker };
})();
