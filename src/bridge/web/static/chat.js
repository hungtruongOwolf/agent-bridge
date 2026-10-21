/* One chat = one small office. This file runs the three screens (market floor, chat office, memory), the conversation,
   "what the helper sees" (the memory tree with tick boxes) and the helper profile. Plain language only; every string from
   the server is inserted with textContent, never as markup. */
(function () {
  "use strict";
  let B = null;          // shared helpers from app.js
  let cur = null;        // the open chat (as the server describes it)
  let ctx = null;        // the latest "what the helper will see" preview
  let office = null;     // the pixel office of the open chat
  let view = "office", pendingText = "", progressLines = [], progressTimer = null, ctxKey = "", sending = false, sendingId = null, draftTimer = null, pendingApproval = null;
  const sideOpen = new Set();
  let moreOpen = false;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const btn = (text, cls, fn) => { const b = el("button", cls || "btn", text); b.type = "button"; if (fn) b.onclick = fn; return b; };
  const say = (t) => { const n = $("chatnote"); if (n) n.textContent = t || ""; };
  const caption = (t) => { $("caption").textContent = t; $("floor").setAttribute("aria-label", t); };

  /* ---------- screens ---------- */
  function showView(name) {
    view = name;
    ["office", "chat", "studio", "memory"].forEach((v) => { $("view-" + v).hidden = v !== name; });
    ["office", "studio", "memory"].forEach((v) => {
      const on = v === name || (v === "office" && name === "chat"), t = $("tab-" + v);
      t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1;
    });
    try { sessionStorage.setItem("ab-view", name === "chat" ? "office" : name); } catch (e) { /* remembering the tab is optional */ }
    if (name === "office") { window.Market.start(); window.MemoryUI.redraw(); } else window.Market.stop();
    if (name === "memory") window.MemoryUI.show();
    if (name === "studio") window.Studio.show();
    if (name === "chat" && office) window.dispatchEvent(new Event("resize"));
  }

  /* ---------- opening and starting chats ---------- */
  async function open(id) {
    showView("chat"); ensureOffice();
    try { cur = await B.api("/api/thread?id=" + encodeURIComponent(id)); } catch (e) { say(e.message); cur = null; showView("office"); return; }
    ctxKey = ""; ctx = null; pendingApproval = pendingApproval && pendingApproval.threadId === cur.id ? pendingApproval : null;
    drawConversation(); setOffice(); await loadContext(); $("draft").focus();
  }

  async function startNew(key) {
    try { const t = await B.api("/api/threads", { agent_key: key }); await B.refresh(); await open(t.id); }
    catch (e) { say(e.message); }
  }
  async function startWith(key, text) { await startNew(key); if (cur) { $("draft").value = text; $("draft").focus(); loadContext(); } }

  function back() { cur = null; clearInterval(progressTimer); showView("office"); }

  /* ---------- the small office ---------- */
  function ensureOffice() {
    if (office) return;
    office = new window.Office($("floor"), { onDrawer: (path) => toggleShelf(path) });
    office.pace = 1.6;
  }
  function agentInfo() { return cur && cur.agent && cur.agent.available ? { id: cur.agent.id, name: cur.agent.name, status: cur.agent.status } : null; }
  function setOffice() {
    if (!office || !cur) return;
    office.showIdle(agentInfo()); drawDrawers();
    $("officetitle").textContent = cur.agent.available ? cur.agent.name + "'s office" : "This chat's office";
    caption(cur.messages.length ? "Here is what the helper just did." : "Waiting for your question.");
  }
  function drawDrawers() {
    if (!office) return;
    const top = (ctx ? ctx.shelves : []).filter((s) => s.depth === 0).slice(0, 4);
    office.setDrawers(top.map((s) => ({ type: s.path, label: s.name, count: s.count, open: s.state !== "closed", locked: s.secret > 0 })));
  }
  const topShelf = (p) => (p && p.includes("/") ? p.slice(0, p.indexOf("/")) : p);
  async function replay(report) {
    if (!office || !cur || !report || !report.journal) return;
    let recs = new Map();
    try {
      if (report.records_handed && report.records_handed.length) {
        (await B.api("/api/memory?limit=100&ids=" + report.records_handed.slice(0, 50).map(encodeURIComponent).join(","))).items.forEach((r) => recs.set(r.id, { type: topShelf(r.shelf), sensitivity: r.sensitivity }));
      }
    } catch (e) { /* the picture still plays without file positions */ }
    const mine = cur.id;
    try { await office.play(report, { animate: true, records: recs, log: () => {}, caption: (t) => { if (cur && cur.id === mine) caption(t); } }); } catch (e) { /* the answer is already on screen */ }
  }

  /* ---------- the open chat ---------- */
  function drawConversation() {
    const box = $("convo"); box.replaceChildren();
    $("composer").hidden = !cur; $("sidepanel").hidden = !cur;
    if (!cur) { $("budgetline").textContent = ""; say(""); $("convohead").replaceChildren(); return; }
    const head = $("convohead"); head.replaceChildren();
    const a = cur.agent;
    const title = el("div"); title.append(el("div", "h", cur.title), el("div", "muted small", a.available ? "with " + a.name + " · " + B.cents(a.price_cents) + " per answer" : "This helper is no longer available."));
    const acts = el("div", "acts");
    if (a.available) acts.append(btn("Meet " + a.name, "btn", () => profile(a.key)));
    head.append(title, acts);
    if (!cur.messages.length) box.append(el("p", "empty", "Type your question below. Tick a shelf on the left if the helper should use your files."));
    cur.messages.forEach((m) => box.append(bubble(m)));
    if (pendingApproval && pendingApproval.threadId === cur.id) {
      if (pendingApproval.text) { const u = el("div", "msg user"); u.append(el("div", "text", pendingApproval.text)); box.append(u); }
      box.append(approvalCard());
    }
    if (sending && sendingId === cur.id) {
      if (pendingText) { const u = el("div", "msg user"); u.append(el("div", "text", pendingText)); box.append(u); }
      const w = el("div", "msg helper thinking"); w.id = "workbubble"; w.append(el("div", "text", "Working on it…"), el("div", "small muted", progressLines.join(" ")));
      box.append(w);
    }
    box.scrollTop = box.scrollHeight;
    const waiting = (pendingApproval && pendingApproval.threadId === cur.id) || (sending && sendingId === cur.id);
    if (cur.busy && !waiting) { const r = el("div", "msg system"); r.append(el("div", "text", "This chat still looks busy, maybe because the page was reloaded."), btn("Reset this chat", "btn", resetBusy)); box.append(r); }
    $("send").disabled = waiting || cur.busy || !a.available;
    drawBudget();
  }

  function bubble(m) {
    const d = el("div", "msg " + m.role);
    d.append(el("div", "text", m.text));
    const meta = el("div", "meta small muted");
    if (m.role === "helper") {
      if (m.risk) meta.append(el("span", "tag " + (m.risk === "high" ? "bad" : m.risk === "medium" ? "wait" : "good"), "worry level: " + m.risk), " ");
      if (m.files && m.files.length) {
        const f = el("details", "based"); f.append(el("summary", null, "Written from " + m.files.length + " of your files"));
        f.addEventListener("toggle", async () => {
          if (!f.open || f.dataset.done) return; f.dataset.done = "1";
          try {
            const got = (await B.api("/api/memory?limit=100&ids=" + m.files.slice(0, 50).map(encodeURIComponent).join(","))).items, by = new Map(got.map((r) => [r.id, r]));
            m.files.forEach((id) => { const r = by.get(id); f.append(el("div", "small", r ? r.shelf_name + ": " + (r.long ? "“" + r.title + "” (long note)" : r.text) : "A file you have since deleted")); });
          } catch (e) { f.append(el("div", "small muted", e.message)); }
        });
        d.append(f);
      } else meta.append("Written without any of your files. ");
      if (m.run_id) {
        const how = el("details", "based"); how.append(el("summary", null, "How this answer was made"));
        how.addEventListener("toggle", async () => {
          if (!how.open || how.dataset.done) return; how.dataset.done = "1";
          try { const r = await B.api("/api/how?run_id=" + encodeURIComponent(m.run_id)); r.steps.forEach((t) => how.append(el("div", "small", "• " + t))); }
          catch (e) { how.append(el("div", "small muted", e.message)); }
        });
        d.append(how);
      }
      if (m.proposals) meta.append(window.plural(m.proposals, "suggestion") + " to remember " + (m.proposals === 1 ? "is" : "are") + " waiting under My office. ");
    }
    if (m.payment) {
      const p = m.payment;
      meta.append(p.state === "SETTLED" ? "Paid " + B.cents(p.captured) : p.state === "SETTLED_REJECTED" ? "Marked not helpful, paid " + B.cents(p.captured) : p.state === "RESULT_READY" ? "Unless you press “Not helpful”, you pay the rest when you send your next message" : p.captured ? "Paid " + B.cents(p.captured) : "Not charged");
      if (p.can_reject) meta.append(" ", btn("Not helpful", "linkbtn", () => act("/api/thread/reject", { id: cur.id, message_id: m.id })));
    }
    if (m.role !== "system" || !m.run_id) meta.append(" ", btn("Forget this message", "linkbtn", () => act("/api/thread/forget", { id: cur.id, message_id: m.id })));
    if (meta.childNodes.length) d.append(meta);
    return d;
  }

  async function resetBusy() {
    try { await B.api("/api/thread/settings", { id: cur.id, reset_busy: true }); cur = await B.api("/api/thread?id=" + cur.id); drawConversation(); } catch (e) { say(e.message); }
  }

  async function act(path, body) {
    try { const r = await B.api(path, body); if (r.messages) cur = r; else cur = await B.api("/api/thread?id=" + cur.id); await B.refresh(); drawConversation(); loadContext(); }
    catch (e) { say(e.message); }
  }

  function drawBudget() {
    const b = cur.budget, n = $("budgetline");
    n.textContent = "Spent so far: " + B.cents(b.spent) + (b.held ? " (+" + B.cents(b.held) + " on hold)" : "") + " of " + B.cents(b.limit) + ".";
  }

  /* ---------- sending ---------- */
  async function send(ev) {
    ev.preventDefault();
    const box = $("draft"), text = box.value.trim();
    if (!cur || sending || !text) return;
    const mine = cur.id; sending = true; sendingId = mine; pendingText = text; progressLines = []; say(""); drawConversation(); watchProgress(mine);
    if (office) { office.showIdle(agentInfo()); drawDrawers(); office.say("agent", "Let me see…", 3000); caption("The helper is working on your message."); }
    let report = null;
    try {
      const r = await B.api("/api/thread/send", { id: mine, text, simulate: false });
      box.value = "";
      if (r.needs_approval) { pendingApproval = Object.assign({ threadId: mine, text }, r); caption("Waiting for you to approve the hold on the payment page."); }
      if (cur && cur.id === mine) cur = r.thread;
      report = r.report || null;
    } catch (e) { say(e.message); try { const t = await B.api("/api/thread?id=" + mine); if (cur && cur.id === mine) cur = t; } catch (_) { /* keep what is on screen */ } }
    sending = false; sendingId = null; pendingText = ""; clearInterval(progressTimer);
    try { await B.refresh(); } catch (_) { /* the screen already shows the answer */ }
    drawConversation(); loadContext();
    if (report && cur && cur.id === mine) replay(report);
  }

  function watchProgress(id) {
    clearInterval(progressTimer);
    progressTimer = setInterval(async () => {
      if (!sending || sendingId !== id) { clearInterval(progressTimer); return; }
      try {
        const p = await B.api("/api/thread/progress?id=" + encodeURIComponent(id));
        progressLines = p.steps;
        const w = $("workbubble"); if (w && w.lastChild) w.lastChild.textContent = p.steps.length ? p.steps[p.steps.length - 1] : "";
        if (p.steps.length) caption(p.steps[p.steps.length - 1]);
      } catch (e) { /* the answer itself will report problems */ }
    }, 900);
  }

  async function continueApproved() {
    const p = pendingApproval; if (!p || sending) return;
    sending = true; sendingId = p.threadId; drawConversation();
    let report = null;
    try { const r = await B.api("/api/run/continue", { run_id: p.run_id }); pendingApproval = null; if (cur && cur.id === p.threadId) cur = r.thread; report = r.report; }
    catch (e) { say(e.message + " If this keeps happening, press Cancel and send the message again."); }
    sending = false; sendingId = null;
    try { await B.refresh(); } catch (_) { /* optional */ }
    drawConversation(); loadContext();
    if (report && cur && cur.id === p.threadId) replay(report);
  }

  function approvalCard() {
    const p = pendingApproval, d = el("div", "msg system");
    d.append(el("div", "text", "Before the helper starts, approve a hold of " + B.cents(p.price) + " on the payment page. Nothing is charged until there is an answer."));
    const acts = el("div", "acts");
    if (/^https?:\/\//.test(p.approve_url || "")) { const a = document.createElement("a"); a.href = p.approve_url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "btn go2"; a.textContent = "Open the approval page"; acts.append(a); }
    acts.append(btn("I approved, continue", "btn", continueApproved), btn("Cancel", "btn warn", async () => {
      try { await B.api("/api/thread/cancel", { run_id: p.run_id }); } catch (e) { say(e.message); }
      pendingApproval = null;
      try { cur = await B.api("/api/thread?id=" + p.threadId); await B.refresh(); } catch (_) { /* optional */ }
      drawConversation();
    }));
    d.append(acts, el("div", "small muted", "When you approve on the other page, this chat carries on by itself.")); return d;
  }

  /* the approval page tells this tab when the buyer is done */
  function listenForApproval() {
    const onMsg = (what) => { if (what === "approved" && pendingApproval) continueApproved(); else if (what === "cancelled" && pendingApproval) say("The hold was cancelled on the payment page. Press Cancel here, then send your message again."); };
    try { const ch = new BroadcastChannel("agent-bridge-paypal"); ch.onmessage = (e) => onMsg(e.data); } catch (e) { /* older browsers use the storage event below */ }
    window.addEventListener("storage", (e) => { if (e.key === "agent-bridge-paypal" && e.newValue) onMsg(String(e.newValue).split(":")[0]); });
  }

  /* ---------- what the helper will see: the memory tree with tick boxes ---------- */
  async function loadContext() {
    if (!cur) return;
    const mine = cur.id;
    try {
      const c = await B.api("/api/thread/context?id=" + encodeURIComponent(mine) + "&draft=" + encodeURIComponent($("draft").value.slice(0, 300)));
      if (!cur || cur.id !== mine) return;
      const key = JSON.stringify([c.shelves.map((s) => [s.path, s.state, s.count, s.shared]), c.shared.map((f) => f.id), c.held_back.map((f) => f.id), c.likely, c.walk, c.suggest, c.history.length, cur.lens, cur.history_turns, cur.budget.limit]);
      const changed = key !== ctxKey; ctx = c; ctxKey = key;
      if (changed) { drawSide(); drawHint(); drawDrawers(); }
    } catch (e) { say(e.message); }
  }

  function drawHint() {
    const h = $("hint"); h.replaceChildren();
    if (!cur) return;
    if (!cur.lens.shelves.length && !cur.lens.include.length) h.append(el("span", "small muted", "No shelf is ticked, so it will answer from your message alone."));
    (ctx.suggest || []).forEach((s) => {
      const row = el("span", "suggestion"); row.append(el("span", "small", "This may need “" + s.name + "”. "), btn("Tick it", "btn go2", () => openShelf(s.path)));
      h.append(row);
    });
  }

  const isInherited = (s) => s.state === "open" && !cur.lens.shelves.includes(s.path);
  function visibleShelf(s) {
    for (let p = s.parent; p; p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "") if (!sideOpen.has(p)) return false;
    return true;
  }
  async function openShelf(path) { return setSettings({ shelves: [...cur.lens.shelves.filter((p) => !(p.startsWith(path + "/"))), path].filter((p, i, a) => a.indexOf(p) === i) }); }
  async function toggleShelf(path) {
    if (!cur || !ctx) return;
    const s = ctx.shelves.find((x) => x.path === path); if (!s) return;
    if (cur.lens.shelves.includes(path)) return setSettings({ shelves: cur.lens.shelves.filter((p) => p !== path) });
    if (s.state === "open") return;  // open because a shelf above it is open
    return openShelf(path);
  }

  function drawSide() {
    const box = $("sidebody"); box.replaceChildren();
    box.append(el("p", "small", "Tick the shelves this helper may look at."));

    const tree = el("ul", "shelves sidetree");
    if (!ctx.shelves.length) tree.append(el("li", "empty", "Your memory is empty. Add notes in My memory."));
    ctx.shelves.filter(visibleShelf).forEach((s) => {
      const li = el("li"); li.style.paddingLeft = (s.depth * 14) + "px";
      const tg = s.has_children ? btn(sideOpen.has(s.path) ? "▾" : "▸", "twist", () => { sideOpen.has(s.path) ? sideOpen.delete(s.path) : sideOpen.add(s.path); drawSide(); }) : el("span", "twist");
      const lab = el("label", "shelfpick" + (s.state === "open" ? " on" : s.state === "partly" ? " part" : "")), c = document.createElement("input");
      c.type = "checkbox"; c.checked = s.state === "open"; c.indeterminate = s.state === "partly"; c.disabled = isInherited(s);
      c.setAttribute("aria-label", "Let the helper see " + s.name + (isInherited(s) ? " (open because a shelf above it is open)" : ""));
      c.onchange = () => toggleShelf(s.path);
      lab.append(c, el("span", "sn", s.name), el("span", "cnt", String(s.count)));
      if (s.secret) lab.append(el("span", "tag wait", s.secret + " secret"));
      li.append(tg, lab); tree.append(li);
    });
    box.append(tree);

    box.append(el("p", "seesum", ctx.shared_count ? "It can see " + ctx.shared_count + " file" + (ctx.shared_count === 1 ? "" : "s") + "." : "It can see nothing yet, so it answers from your message alone."));
    if (ctx.walk && ctx.walk.length) box.append(el("p", "small walk", "For your message it would look in: " + ctx.walk.join(", ") + "."));
    if (ctx.secret) box.append(el("p", "small muted", "🔒 " + ctx.secret + " secret file" + (ctx.secret === 1 ? " is" : "s are") + " never shared."));
    const more = el("details", "more"); more.open = moreOpen; more.addEventListener("toggle", () => { moreOpen = more.open; }); more.append(el("summary", null, "More settings"));
    more.append(el("h3", "sub", "Every file it can see (" + ctx.shared_count + ")"));
    const ul = el("ul", "filelist");
    ctx.shared.forEach((f) => {
      const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = true; c.setAttribute("aria-label", "Share: " + f.text);
      c.onchange = () => setSettings({ exclude: [...cur.lens.exclude, f.id], include: cur.lens.include.filter((x) => x !== f.id) });
      const t = el("span", null, f.text); li.append(c, t);
      if (ctx.likely.includes(f.id)) li.append(el("span", "tag good", "matches your message"));
      ul.append(li);
    });
    if (!ctx.shared.length) ul.append(el("li", "empty", "Nothing. The helper will answer from your message alone."));
    if (ctx.shared_more) ul.append(el("li", "empty", "…and " + ctx.shared_more + " more."));
    more.append(ul);

    if (ctx.held_back.length) {
      more.append(el("h3", "sub", "You held these back (" + ctx.held_back.length + ")"));
      const lk = el("ul", "filelist locked");
      ctx.held_back.forEach((f) => {
        const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = false; c.setAttribute("aria-label", "Share again: " + f.text);
        c.onchange = () => setSettings({ exclude: cur.lens.exclude.filter((x) => x !== f.id) });
        li.append(c, el("span", null, f.shelf_name + ": " + f.text)); lk.append(li);
      });
      more.append(lk);
    }

    const h = el("div", "setrow"); h.append(el("label", "small", "The helper remembers the last "));
    const num = document.createElement("input"); num.type = "number"; num.min = 0; num.max = 10; num.value = cur.history_turns; num.id = "histturns"; num.setAttribute("aria-label", "How many earlier messages the helper is shown");
    num.onchange = () => setSettings({ history_turns: parseInt(num.value, 10) }); h.append(num, el("span", "small", " messages of this chat."));
    more.append(h);
    more.append(el("p", "small muted", ctx.history.length ? "Right now it would see " + ctx.history.length + " earlier message(s)." : "Right now it would see no earlier messages."));

    const bd = el("div", "setrow"); bd.append(el("label", "small", "Most this chat may spend (cents) "));
    const lim = document.createElement("input"); lim.type = "number"; lim.min = 0; lim.max = 10000; lim.step = 10; lim.value = cur.budget.limit; lim.setAttribute("aria-label", "Spending limit in cents");
    lim.onchange = () => setSettings({ budget_cents: parseInt(lim.value, 10) }); bd.append(lim); more.append(bd);

    more.append(el("p", "small muted", ctx.goes_to_the_brain));
    const dng = el("div", "acts");
    dng.append(btn("Clear this chat", "btn", (e) => confirmTwice(e.target, "Really clear?", () => act("/api/thread/clear", { id: cur.id }))),
      btn("Delete this chat", "btn warn", (e) => confirmTwice(e.target, "Really delete?", async () => { try { await B.api("/api/thread/delete", { id: cur.id }); await B.refresh(); back(); } catch (er) { say(er.message); } })));
    more.append(dng);
    box.append(more);
  }

  function confirmTwice(b, label, fn) {
    if (b.dataset.armed) { fn(); return; }
    const old = b.textContent; b.dataset.armed = "1"; b.textContent = label;
    setTimeout(() => { delete b.dataset.armed; b.textContent = old; }, 4000);
  }

  async function setSettings(patch) {
    ctxKey = "";
    try { cur = await B.api("/api/thread/settings", Object.assign({ id: cur.id }, patch)); await B.refresh(); drawConversation(); await loadContext(); }
    catch (e) { say(e.message); await loadContext(); }
  }

  /* ---------- meet a helper ---------- */
  async function profile(key) {
    const dlg = $("profile"), body = $("profilebody"); body.replaceChildren(el("p", null, "Loading…"));
    if (!dlg.open) dlg.showModal();
    let p; try { p = await B.api("/api/agent?key=" + encodeURIComponent(key)); } catch (e) { body.replaceChildren(el("p", null, e.message)); return; }
    body.replaceChildren();
    const name = B.niceName(p.id);
    body.append(el("h2", null, "Meet " + name), el("p", null, p.summary));
    if (p.speciality) body.append(el("p", "muted", "Best at: " + p.speciality));
    body.append(el("p", "small", B.cents(p.price_cents) + " per answer · " + p.stars + " fans · version " + p.version));

    body.append(el("h3", "sub", "What it can do"));
    p.author_says.skills.forEach((s) => {
      const d = el("div", "skill"); d.append(el("div", "name", s.name), el("div", null, s.does));
      const q = el("div", "small muted"); q.append("Try asking: ");
      (s.try_asking || []).forEach((t) => { q.append(btn("“" + t + "”", "linkbtn", async () => { $("profile").close(); await startWith(key, t); }), " "); });
      d.append(q); body.append(d);
    });
    if (p.author_says.good_to_know && p.author_says.good_to_know.length) {
      body.append(el("h3", "sub", "Good to know"));
      const ul = el("ul"); p.author_says.good_to_know.forEach((t) => ul.append(el("li", null, t))); body.append(ul);
    }
    const safety = el("details", "more"); safety.append(el("summary", null, "What it touches and what it can never do"));
    const w = el("ul"); p.works_with.forEach((x) => w.append(el("li", null, x.text))); safety.append(w);
    const c = el("ul"); p.cannot.forEach((x) => c.append(el("li", null, x))); safety.append(c); body.append(safety);

    body.append(el("h3", "sub", "How well it did in tests"));
    const m = p.measured;
    if (!m.tested) body.append(el("p", null, m.note));
    else if (m.violations) body.append(el("p", "tag bad", "Caught cheating during testing: " + m.violations.map((v) => (B.blocked[v] || v)).join("; ")));
    else {
      body.append(el("p", null, "Passed " + m.passes + " of " + m.total + " test questions. How much to trust it: " + m.score + " out of 100." + (m.infra_failures ? " " + m.infra_failures + " run(s) were thrown out because the thinking service was down." : "")));
      m.by_skill.forEach((s) => { const r = el("div", "skillrow"); r.append(el("span", null, s.what), el("b", null, s.passes + " of " + s.total)); body.append(r); if (s.ask) body.append(el("div", "small muted", "Test question: “" + s.ask + "”")); });
    }
    const go = btn("Chat with " + name, "btn go2", async () => { dlg.close(); await startNew(key); });
    body.append(el("div", "acts", ""), go);
  }

  /* ---------- start ---------- */
  function mount(bridge) {
    B = bridge;
    $("tab-office").parentNode.addEventListener("keydown", (e) => {
      const tabs = ["office", "studio", "memory"], i = tabs.findIndex((n) => $("tab-" + n) === document.activeElement);
      if (i < 0) return; let j = i;
      if (e.key === "ArrowRight") j = (i + 1) % 3; else if (e.key === "ArrowLeft") j = (i + 2) % 3; else if (e.key === "Home") j = 0; else if (e.key === "End") j = 2; else return;
      e.preventDefault(); showView(tabs[j]); $("tab-" + tabs[j]).focus();
    });
    $("tab-office").onclick = () => showView("office"); $("tab-studio").onclick = () => showView("studio"); $("tab-memory").onclick = () => showView("memory");
    $("backtofloor").onclick = back;
    $("composer").onsubmit = send; listenForApproval();
    $("draft").oninput = () => { clearTimeout(draftTimer); draftTimer = setTimeout(loadContext, 350); };
    $("draft").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); } };
    $("profileclose").onclick = () => $("profile").close();
    let v = "office"; try { v = sessionStorage.getItem("ab-view") || "office"; } catch (e) { /* default tab */ }
    showView(v === "memory" || v === "studio" ? v : "office");
  }
  window.ChatUI = { mount, profile, startWith, startNew, open, show: showView, redraw: () => { if (view === "chat" && cur) { drawBudget(); } } };
})();
