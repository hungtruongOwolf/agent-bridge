/* Chats, "what the helper sees", "my memory" and the helper profile. Plain language only; every string from the server is
   inserted with textContent, never as markup. */
(function () {
  "use strict";
  let B = null;          // shared helpers from app.js
  let cur = null;        // the open chat (as the server describes it)
  let ctx = null;        // the latest "what the helper will see" preview
  let pendingText = "", progressLines = [], progressTimer = null, ctxKey = "", sending = false, sendingId = null, draftTimer = null, pendingApproval = null;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const btn = (text, cls, fn) => { const b = el("button", cls || "btn", text); b.type = "button"; if (fn) b.onclick = fn; return b; };
  const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");
  const LEVEL_NAME = { low: "everyday", medium: "personal", high: "secret" };
  const say = (t) => { const n = $("chatnote"); if (n) n.textContent = t || ""; };

  /* ---------- tabs ---------- */
  function showView(name) {
    ["chat", "memory", "office"].forEach((v) => {
      const on = v === name; $("view-" + v).hidden = !on;
      const t = $("tab-" + v); t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1;
    });
    try { sessionStorage.setItem("ab-view", name); } catch (e) { /* remembering the tab is optional */ }
    if (name === "memory") drawMemory();
    if (name === "chat") drawThreads();
    if (name === "office" && window.dispatchEvent) window.dispatchEvent(new Event("resize"));
  }

  /* ---------- chat list and new chat ---------- */
  function drawThreads() {
    const S = B.state(), ul = $("threads"); ul.replaceChildren();
    if (!S.threads.length) ul.append(el("li", "empty", "No chats yet. Start one with a helper you like."));
    S.threads.forEach((t) => {
      const li = el("li"); li.setAttribute("aria-current", String(!!(cur && cur.id === t.id)));
      const b = el("button", "threadbtn"); b.type = "button";
      const m = S.market.find((x) => x.key === t.agent_key);
      b.append(el("span", "name", t.title), el("span", "blurb", (m ? B.niceName(m.id) + ": " : "") + (t.last || "No messages yet")));
      b.onclick = () => openThread(t.id);
      li.append(b); ul.append(li);
    });
  }

  function drawPicker() {
    const S = B.state(), box = $("picker"); box.replaceChildren();
    box.append(el("p", "small muted", "Pick who you want to talk with. Press “Meet” first if you want to know what they can do."));
    const hireable = S.market.filter((m) => m.status !== "flagged");
    if (!hireable.length) box.append(el("p", "empty", "Nobody is available yet."));
    hireable.forEach((m) => {
      const row = el("div", "pick");
      const who = el("div", "who"); who.append(el("span", "name", B.niceName(m.id)), el("span", "blurb", m.summary));
      const skills = (m.skills || []).join(" · ");
      if (skills) who.append(el("span", "blurb skills", skills));
      const acts = el("div", "acts");
      acts.append(btn("Meet", "btn", () => profile(m.key)), btn("Chat, " + B.cents(Math.round(m.price_usd * 100)) + " per answer", "btn go2", () => newThread(m.key)));
      row.append(who, acts); box.append(row);
    });
    const flagged = S.market.filter((m) => m.status === "flagged");
    if (flagged.length) box.append(el("p", "small muted", flagged.length + " helper(s) were caught cheating and cannot be chatted with. You can watch the guard stop them in the Office tab."));
  }

  async function newThread(key) {
    try { const t = await B.api("/api/threads", { agent_key: key }); await B.refresh(); await openThread(t.id); $("picker").hidden = true; } catch (e) { say(e.message); }
  }

  /* ---------- the open chat ---------- */
  async function openThread(id) {
    try { cur = await B.api("/api/thread?id=" + encodeURIComponent(id)); } catch (e) { say(e.message); cur = null; }
    drawThreads(); drawConversation(); await loadContext();
  }

  function drawConversation() {
    const box = $("convo"); box.replaceChildren();
    $("composer").hidden = !cur; $("sidepanel").hidden = !cur;
    if (!cur) { $("budgetline").textContent = ""; say(""); $("convohead").replaceChildren(); box.append(el("p", "empty big", "Choose a chat on the left, or start a new one. A chat is a conversation that keeps going, and you decide what the helper can see.")); return; }
    const head = $("convohead"); head.replaceChildren();
    const a = cur.agent;
    const title = el("div"); title.append(el("div", "h", cur.title), el("div", "muted small", a.available ? "with " + a.name + " · " + B.cents(a.price_cents) + " per answer" : "This helper is no longer available."));
    const acts = el("div", "acts");
    if (a.available) acts.append(btn("Meet " + a.name, "btn", () => profile(a.key)));
    head.append(title, acts);
    if (!cur.messages.length) box.append(el("p", "empty", "Say what you need. For example: “Which of my accounts need attention this week?”"));
    cur.messages.forEach((m) => box.append(bubble(m)));
    if (pendingApproval && pendingApproval.threadId === cur.id) box.append(approvalCard());
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
    const d = el("div", "msg " + m.role); const S = B.state();
    d.append(el("div", "text", m.text));
    const meta = el("div", "meta small muted");
    if (m.role === "helper") {
      if (m.risk) { const t = el("span", "tag " + (m.risk === "high" ? "bad" : m.risk === "medium" ? "wait" : "good"), "worry level: " + m.risk); meta.append(t, " "); }
      if (m.files && m.files.length) {
        const f = el("details", "based"); f.append(el("summary", null, "Written from " + m.files.length + " of your files"));
        m.files.forEach((id) => { const r = S.vault.find((x) => x.id === id); f.append(el("div", "small", r ? r.text : "A file you have since deleted")); });
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
      if (m.proposals) meta.append(m.proposals + " thing(s) to remember are waiting in My memory. ");
    }
    if (m.payment) {
      const p = m.payment;
      meta.append(p.state === "SETTLED" ? "Paid " + B.cents(p.captured) : p.state === "SETTLED_REJECTED" ? "Marked not helpful, paid " + B.cents(p.captured) : p.state === "RESULT_READY" ? "Counts as good when you send your next message" : p.captured ? "Paid " + B.cents(p.captured) : "Not charged");
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
    n.textContent = "This chat has cost " + B.cents(b.spent) + (b.held ? " so far, and " + B.cents(b.held) + " is waiting for your decision" : "") + ". Limit: " + B.cents(b.limit) + ".";
  }

  /* ---------- sending ---------- */
  async function send(ev) {
    ev.preventDefault();
    const box = $("draft"), text = box.value.trim();
    if (!cur || sending || !text) return;
    const mine = cur.id; sending = true; sendingId = mine; pendingText = text; progressLines = []; say(""); drawConversation(); watchProgress(mine);
    try {
      const r = await B.api("/api/thread/send", { id: mine, text, simulate: $("misbehave").checked });
      box.value = "";
      if (r.needs_approval) pendingApproval = Object.assign({ threadId: mine }, r);
      if (cur && cur.id === mine) cur = r.thread;
    } catch (e) { say(e.message); try { const t = await B.api("/api/thread?id=" + mine); if (cur && cur.id === mine) cur = t; } catch (_) { /* keep what is on screen */ } }
    sending = false; sendingId = null; pendingText = ""; clearInterval(progressTimer);
    try { await B.refresh(); } catch (_) { /* the screen already shows the answer */ }
    drawConversation(); loadContext(); drawThreads();
  }

  function watchProgress(id) {
    clearInterval(progressTimer);
    progressTimer = setInterval(async () => {
      if (!sending || sendingId !== id) { clearInterval(progressTimer); return; }
      try {
        const p = await B.api("/api/thread/progress?id=" + encodeURIComponent(id));
        progressLines = p.steps;
        const w = $("workbubble"); if (w && w.lastChild) w.lastChild.textContent = p.steps.length ? p.steps[p.steps.length - 1] : "";
      } catch (e) { /* the answer itself will report problems */ }
    }, 900);
  }

  function approvalCard() {
    const p = pendingApproval, d = el("div", "msg system");
    d.append(el("div", "text", "Before the helper starts, approve a hold of " + B.cents(p.price) + " on the payment page. Nothing is charged until there is an answer."));
    const acts = el("div", "acts");
    if (/^https:\/\//.test(p.approve_url || "")) { const a = document.createElement("a"); a.href = p.approve_url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "btn"; a.textContent = "Open the approval page"; acts.append(a); }
    acts.append(btn("I approved, continue", "btn", async () => {
      sending = true; sendingId = p.threadId; drawConversation();
      try { const r = await B.api("/api/run/continue", { run_id: p.run_id }); pendingApproval = null; if (cur && cur.id === p.threadId) cur = r.thread; }
      catch (e) { say(e.message + " If this keeps happening, press Cancel and send the message again."); }
      sending = false; sendingId = null;
      try { await B.refresh(); } catch (_) { /* optional */ }
      drawConversation(); loadContext();
    }), btn("Cancel", "btn warn", async () => {
      try { await B.api("/api/thread/cancel", { run_id: p.run_id }); } catch (e) { say(e.message); }
      pendingApproval = null;
      try { cur = await B.api("/api/thread?id=" + p.threadId); await B.refresh(); } catch (_) { /* optional */ }
      drawConversation();
    }));
    d.append(acts); return d;
  }

  /* ---------- what the helper will see ---------- */
  async function loadContext() {
    if (!cur) return;
    const mine = cur.id;
    try {
      const c = await B.api("/api/thread/context?id=" + encodeURIComponent(mine) + "&draft=" + encodeURIComponent($("draft").value.slice(0, 300)));
      if (!cur || cur.id !== mine) return;
      const key = JSON.stringify([c.shared.map((f) => f.id), c.locked.map((f) => f.id), c.likely, c.history.length, cur.lens, cur.history_turns, cur.budget.limit]);
      const changed = key !== ctxKey; ctx = c; ctxKey = key;
      if (changed) drawSide();
    } catch (e) { say(e.message); }
  }

  function drawSide() {
    const box = $("sidebody"); box.replaceChildren();
    const S = B.state(), kinds = [...new Set(S.vault.map((r) => r.type))].sort();
    box.append(el("p", "small", "Only what is switched on below, and the last few messages, can reach the helper. Everything else stays locked."));

    const dr = el("fieldset", "seeing"); dr.append(el("legend", "small muted", "Drawers the helper may open"));
    kinds.forEach((t) => {
      const l = el("label"), i = document.createElement("input"); i.type = "checkbox"; i.checked = cur.lens.types.includes(t);
      i.onchange = () => setSettings({ types: kinds.filter((k) => (k === t ? i.checked : cur.lens.types.includes(k))) });
      l.append(i, el("span", null, B.typeLabel(t))); dr.append(l);
    });
    box.append(dr);

    const pv = el("fieldset", "privacy"); pv.append(el("legend", "small muted", "How private is too private?"));
    [["low", "Everyday things only"], ["medium", "Personal things too"], ["high", "Everything, even secrets"]].forEach(([v, t]) => {
      const l = el("label"), i = document.createElement("input"); i.type = "radio"; i.name = "lvl"; i.value = v; i.checked = cur.lens.max_sensitivity === v;
      i.onchange = () => setSettings({ max_sensitivity: v }); l.append(i, el("span", null, t)); pv.append(l);
    });
    box.append(pv);

    box.append(el("h3", "sub", "Files the helper can see (" + ctx.shared.length + ")"));
    const ul = el("ul", "filelist");
    ctx.shared.forEach((f) => {
      const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = true; c.setAttribute("aria-label", "Share: " + f.text);
      c.onchange = () => setSettings({ exclude: [...cur.lens.exclude, f.id], include: cur.lens.include.filter((x) => x !== f.id) });
      const t = el("span", null, f.text); li.append(c, t);
      if (ctx.likely.includes(f.id)) li.append(el("span", "tag good", "matches your message"));
      ul.append(li);
    });
    if (!ctx.shared.length) ul.append(el("li", "empty", "Nothing. The helper will answer from your message alone."));
    box.append(ul);

    if (ctx.locked.length) {
      box.append(el("h3", "sub", "Locked (" + ctx.locked.length + ")"));
      const lk = el("ul", "filelist locked");
      ctx.locked.forEach((f) => {
        const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = false;
        c.setAttribute("aria-label", "Share this " + B.typeLabel(f.type).replace(/s$/, "").toLowerCase() + " file anyway");
        c.onchange = () => setSettings({ include: [...cur.lens.include, f.id], exclude: cur.lens.exclude.filter((x) => x !== f.id) });
        li.append(c, el("span", null, B.typeLabel(f.type).replace(/s$/, "") + ", " + LEVEL_NAME[f.sensitivity] + ". " + f.why)); lk.append(li);
      });
      box.append(lk);
    }

    const h = el("div", "setrow"); h.append(el("label", "small", "The helper remembers the last "));
    const num = document.createElement("input"); num.type = "number"; num.min = 0; num.max = 10; num.value = cur.history_turns; num.id = "histturns"; num.setAttribute("aria-label", "How many earlier messages the helper is shown");
    num.onchange = () => setSettings({ history_turns: parseInt(num.value, 10) }); h.append(num, el("span", "small", " messages of this chat."));
    box.append(h);
    box.append(el("p", "small muted", ctx.history.length ? "Right now it would see " + ctx.history.length + " earlier message(s)." : "Right now it would see no earlier messages."));

    const bd = el("div", "setrow"); bd.append(el("label", "small", "Most this chat may spend (cents) "));
    const lim = document.createElement("input"); lim.type = "number"; lim.min = 0; lim.max = 10000; lim.step = 10; lim.value = cur.budget.limit; lim.setAttribute("aria-label", "Spending limit in cents");
    lim.onchange = () => setSettings({ budget_cents: parseInt(lim.value, 10) }); bd.append(lim); box.append(bd);

    box.append(el("p", "small muted", ctx.goes_to_the_brain));
    const dng = el("div", "acts");
    dng.append(btn("Clear this chat", "btn", () => confirmTwice(dng.firstChild, "Really clear?", () => act("/api/thread/clear", { id: cur.id }))),
      btn("Delete this chat", "btn warn", async (e) => confirmTwice(e.target, "Really delete?", async () => { try { await B.api("/api/thread/delete", { id: cur.id }); cur = null; await B.refresh(); drawThreads(); drawConversation(); } catch (er) { say(er.message); } })));
    box.append(dng);
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

  /* ---------- my memory ---------- */
  function drawMemory() {
    const S = B.state(), box = $("memlist"); box.replaceChildren();
    const sg = $("suggest"); sg.replaceChildren();
    S.proposals.forEach((p) => {
      const n = el("div", "note"); n.append(el("div", null, "“" + p.text + "”"), el("div", "muted small", "A helper suggests you remember this. It is not saved unless you say yes."));
      const a = el("div", "acts");
      a.append(btn("Remember it", "btn", () => decide(p.id, "accept")), btn("No thanks", "btn", () => decide(p.id, "reject")));
      n.append(a); sg.append(n);
    });
    if (!S.vault.length) box.append(el("p", "empty", "Your memory is empty. Add a note above, or say yes to a helper's suggestion."));
    const groups = {};
    S.vault.forEach((r) => (groups[r.type] = groups[r.type] || []).push(r));
    Object.keys(groups).sort().forEach((t) => {
      box.append(el("h3", "sub", B.typeLabel(t) + " (" + groups[t].length + ")"));
      groups[t].forEach((r) => box.append(memCard(r)));
    });
  }

  async function decide(id, action) {
    try { await B.api("/api/proposal", { id, action }); await B.refresh(); drawMemory(); } catch (e) { $("memnote").textContent = e.message; }
  }

  function memCard(r) {
    const c = el("div", "mem");
    c.append(el("div", "memtext", r.text));
    const meta = el("div", "small muted");
    const src = r.source === "helper" ? "Suggested by " + r.helper + ", saved because you said yes" : "Written by you";
    meta.append(src + (r.created ? " on " + when(r.created) : "") + ". " + LEVEL_NAME[r.sensitivity].replace(/^./, (x) => x.toUpperCase()) + ".");
    if (r.edited) meta.append(" You corrected it later.");
    c.append(meta);
    const use = r.used.answers ? "Helped write " + r.used.answers + " answer(s); last in “" + r.used.last_chat + "”." : "Not used in any answer yet.";
    c.append(el("div", "small muted", use));
    const a = el("div", "acts");
    a.append(btn("Edit", "btn", () => editCard(c, r)), btn("Delete", "btn warn", (e) => confirmTwice(e.target, "Really delete?", async () => {
      try { await B.api("/api/memory", { action: "delete", id: r.id }); await B.refresh(); drawMemory(); } catch (er) { $("memnote").textContent = er.message; }
    })));
    c.append(a); return c;
  }

  function editCard(c, r) {
    c.replaceChildren();
    const ta = document.createElement("textarea"); ta.value = r.text; ta.rows = 3; ta.maxLength = 2000; ta.setAttribute("aria-label", "Text of this memory");
    const sel = privacySelect(r.sensitivity);
    const a = el("div", "acts");
    a.append(btn("Save", "btn", async () => {
      try { await B.api("/api/memory", { action: "update", id: r.id, text: ta.value, sensitivity: sel.value }); await B.refresh(); drawMemory(); } catch (e) { $("memnote").textContent = e.message; }
    }), btn("Cancel", "btn", drawMemory));
    c.append(ta, sel, a);
  }

  function privacySelect(v) {
    const s = document.createElement("select"); s.setAttribute("aria-label", "How private this is");
    [["low", "Everyday"], ["medium", "Personal"], ["high", "Secret"]].forEach(([k, t]) => { const o = document.createElement("option"); o.value = k; o.textContent = t; s.append(o); });
    s.value = v || "low"; return s;
  }

  function setupMemoryForm() {
    const f = $("memform"); const sel = privacySelect("low"); sel.id = "memlevel"; $("memlevelslot").replaceChildren(sel);
    f.onsubmit = async (e) => {
      e.preventDefault(); const text = $("memtext").value, type = $("memtype").value.trim().toLowerCase() || "note";
      try { await B.api("/api/memory", { action: "add", type, text, sensitivity: sel.value }); $("memtext").value = ""; $("memnote").textContent = "Saved."; await B.refresh(); drawMemory(); }
      catch (er) { $("memnote").textContent = er.message; }
    };
  }

  /* ---------- bring in a file ---------- */
  function splitNotes(text) {
    const out = [];
    text.replace(/\r\n/g, "\n").split(/\n\s*\n/).forEach((para) => {
      let p = para.trim().replace(/[ \t]+/g, " "); if (!p) return;
      while (p.length > 800) {  // long paragraphs are cut at a sentence end so each note stays readable
        let cut = p.lastIndexOf(". ", 800); if (cut < 200) cut = p.lastIndexOf(" ", 800); if (cut < 200) cut = 800;
        out.push(p.slice(0, cut + 1).trim()); p = p.slice(cut + 1).trim();
      }
      if (p) out.push(p);
    });
    return out;
  }

  function setupImport() {
    $("memfile").onchange = async (ev) => {
      const f = ev.target.files[0], box = $("importbox"); box.replaceChildren(); if (!f) return;
      if (f.size > 300000) { box.append(el("p", "warnline", "That file is bigger than 300 KB. Cut it into smaller parts first.")); return; }
      const notes = splitNotes(await f.text()).slice(0, 50);
      if (!notes.length) { box.append(el("p", "warnline", "There is no text in that file.")); return; }
      box.append(el("p", "small", "Found " + notes.length + " note(s). Untick the ones you do not want."));
      const list = el("ul", "filelist"), boxes = [];
      notes.forEach((t) => { const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = true; c.setAttribute("aria-label", "Keep: " + t.slice(0, 60)); boxes.push(c); li.append(c, el("span", null, t)); list.append(li); });
      const sel = privacySelect("low"), type = document.createElement("input"); type.type = "text"; type.value = "note"; type.size = 10; type.maxLength = 20; type.setAttribute("aria-label", "Which drawer");
      const row = el("div", "composerrow"); row.append(el("label", "small", "Drawer "), type, sel);
      const save = btn("Save the ticked notes", "btn go2", async () => {
        const keep = notes.filter((_, i) => boxes[i].checked); if (!keep.length) { $("memnote").textContent = "Tick at least one note."; return; }
        save.disabled = true;
        try { await B.api("/api/memory", { action: "add_many", items: keep, sensitivity: sel.value, type: type.value.trim().toLowerCase() || "note" }); box.replaceChildren(); $("memfile").value = ""; $("memnote").textContent = "Saved " + keep.length + " note(s)."; await B.refresh(); drawMemory(); }
        catch (e) { $("memnote").textContent = e.message; save.disabled = false; }
      });
      box.append(list, row, save);
    };
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

    body.append(el("h3", "sub", "What it says it can do"), el("p", "small muted", "These are the author's own words. The test results further down show whether they hold up."));
    p.author_says.skills.forEach((s) => {
      const d = el("div", "skill"); d.append(el("div", "name", s.name), el("div", null, s.does));
      const q = el("div", "small muted"); q.append("Try asking: ");
      (s.try_asking || []).forEach((t) => { const b = btn("“" + t + "”", "linkbtn", async () => { $("profile").close(); await startWith(key, t); }); q.append(b, " "); });
      d.append(q); body.append(d);
    });
    if (p.author_says.good_to_know && p.author_says.good_to_know.length) {
      body.append(el("h3", "sub", "Good to know"));
      const ul = el("ul"); p.author_says.good_to_know.forEach((t) => ul.append(el("li", null, t))); body.append(ul);
    }
    body.append(el("h3", "sub", "What it touches (we check this ourselves)"));
    const w = el("ul"); p.works_with.forEach((x) => w.append(el("li", null, x.text))); body.append(w);
    body.append(el("h3", "sub", "What it can never do"));
    const c = el("ul"); p.cannot.forEach((x) => c.append(el("li", null, x))); body.append(c);

    body.append(el("h3", "sub", "What was actually measured"));
    const m = p.measured;
    if (!m.tested) body.append(el("p", null, m.note));
    else if (m.violations) body.append(el("p", "tag bad", "Caught cheating during testing: " + m.violations.map((v) => (B.blocked[v] || v)).join("; ")));
    else {
      body.append(el("p", null, "Passed " + m.passes + " of " + m.total + " test questions. How much to trust it: " + m.score + " out of 100." + (m.infra_failures ? " " + m.infra_failures + " run(s) were thrown out because the thinking service was down." : "")));
      m.by_skill.forEach((s) => { const r = el("div", "skillrow"); r.append(el("span", null, s.what), el("b", null, s.passes + " of " + s.total)); body.append(r); if (s.ask) body.append(el("div", "small muted", "Test question: “" + s.ask + "”")); });
    }
    const go = btn("Chat with " + name, "btn go2", async () => { dlg.close(); showView("chat"); await newThread(key); });
    body.append(el("div", "acts", ""), go);
  }

  async function startWith(key, text) {
    showView("chat"); await newThread(key); $("draft").value = text; $("draft").focus(); loadContext();
  }

  /* ---------- start ---------- */
  function mount(bridge) {
    B = bridge;
    $("tab-chat").parentNode.addEventListener("keydown", (e) => {
      const tabs = ["chat", "memory", "office"], i = tabs.findIndex((n) => $("tab-" + n) === document.activeElement);
      if (i < 0) return; let j = i;
      if (e.key === "ArrowRight") j = (i + 1) % 3; else if (e.key === "ArrowLeft") j = (i + 2) % 3; else if (e.key === "Home") j = 0; else if (e.key === "End") j = 2; else return;
      e.preventDefault(); showView(tabs[j]); $("tab-" + tabs[j]).focus();
    });
    $("tab-chat").onclick = () => showView("chat"); $("tab-memory").onclick = () => showView("memory"); $("tab-office").onclick = () => showView("office");
    $("newchat").onclick = () => { const p = $("picker"); p.hidden = !p.hidden; if (!p.hidden) drawPicker(); };
    $("composer").onsubmit = send;
    $("draft").oninput = () => { clearTimeout(draftTimer); draftTimer = setTimeout(loadContext, 350); };
    $("draft").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); } };
    $("profileclose").onclick = () => $("profile").close();
    setupMemoryForm(); setupImport(); drawPicker();
    let v = "chat"; try { v = sessionStorage.getItem("ab-view") || "chat"; } catch (e) { /* default tab */ }
    showView(v); drawConversation();
    if (!B.state().threads.length) $("picker").hidden = false;
  }
  window.ChatUI = { mount, profile, startWith, redraw: () => { drawThreads(); if (!$("view-memory").hidden) drawMemory(); } };
})();
