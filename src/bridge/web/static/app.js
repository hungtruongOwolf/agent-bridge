/* Agent Bridge console: everything the person clicks and reads. Plain language throughout. */
(function () {
  "use strict";
  const TOKEN = document.body.dataset.token;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const LEVEL = { low: 0, medium: 1, high: 2 };
  const LEVEL_NAME = { low: "everyday", medium: "personal", high: "secret" };
  const TYPE_LABEL = { note: "Notes", contact: "Contacts", finance: "Money" };
  const BAD = {
    OFF_LENS_QUERY: "asked for private files", UNKNOWN_ID: "tried to open files it was not given", CANARY_HIT: "grabbed a decoy file",
    READ_BUDGET: "asked for too many files", SANDBOX_NETWORK: "tried to send messages out of the glass room",
    SANDBOX_PROCESS: "tried to start other programs", SANDBOX_WRITE: "tried to write outside its notebook",
    WEB_QUERY_LEAK: "tried to put your files into a web search"
  };
  const NOTE = { run_started: "Job started", step_started: "Started a step", step_committed: "Finished a step", model_call: "Asked the Brain",
    cell_run: "Ran the helper's program", incident: "Alarm raised", web_search: "Looked something up on the web", model_error: "The Brain was busy",
    run_finished: "Job ended" };
  let S = null, selected = null, running = false, office = null, lastRep = null, voiceOn = false, recognition = null;

  const typeLabel = (t) => TYPE_LABEL[t] || (t.charAt(0).toUpperCase() + t.slice(1) + "s");
  const cents = (c) => c + "¢";
  const priceOf = (m) => Math.round(m.price_usd * 100);

  async function api(path, body) {
    const r = await fetch(path, body ? { method: "POST", headers: { "X-Bridge-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Something went wrong (" + r.status + ").");
    return j;
  }

  /* ---------- what the helper may look at ---------- */
  const types = () => [...document.querySelectorAll("#seeing input:checked")].map((i) => i.value);
  const level = () => document.querySelector("#privacy input:checked").value;
  const shared = (r) => types().includes(r.type) && LEVEL[r.sensitivity] <= LEVEL[level()];

  function drawLens(keep) {
    const prev = keep ? new Set(types()) : null;
    const kinds = [...new Set(S.vault.map((r) => r.type))].sort();
    const box = $("seeing"); box.replaceChildren();
    kinds.forEach((t) => {
      const n = S.vault.filter((r) => r.type === t).length;
      const l = el("label"), i = document.createElement("input"); i.type = "checkbox"; i.value = t;
      i.checked = prev ? prev.has(t) : (t === "note" || t === "contact");
      i.onchange = lensChanged; l.append(i, el("span", null, typeLabel(t) + " (" + n + ")")); box.append(l);
    });
    lensChanged();
  }

  function lensChanged() {
    const list = S.vault, shown = list.filter(shared);
    $("count").textContent = "The helper will see " + shown.length + " of your " + list.length + " files. The rest stay locked in the safe.";
    const ul = $("files"); ul.replaceChildren();
    list.forEach((r) => {
      const li = el("li"); const on = shared(r);
      li.append(el("span", null, on ? "Can see: " : "Locked: "), document.createTextNode(on ? r.text : typeLabel(r.type).replace(/s$/, "") + ", " + LEVEL_NAME[r.sensitivity]));
      if (r.trust === 1) li.append(el("div", "muted small", "Saved from a helper's suggestion because you said yes."));
      ul.append(li);
    });
    if (office) office.setDrawers(drawers());
  }
  function drawers() {
    const kinds = [...new Set(S.vault.map((r) => r.type))].sort(), open = types();
    return kinds.map((t) => {
      const rs = S.vault.filter((r) => r.type === t), isOpen = open.includes(t);
      return { type: t, label: typeLabel(t), count: rs.length, open: isOpen, locked: isOpen && rs.some((r) => LEVEL[r.sensitivity] > LEVEL[level()]) || (!isOpen && rs.every((r) => r.sensitivity === "high")) };
    });
  }
  function toggleType(t) { const i = [...document.querySelectorAll("#seeing input")].find((x) => x.value === t); if (i) { i.checked = !i.checked; lensChanged(); } }

  /* ---------- the people you can hire ---------- */
  function portrait(canvas, m) {
    const c = canvas.getContext("2d"); c.imageSmoothingEnabled = false; c.clearRect(0, 0, 22, 26);
    c.fillStyle = "#F4E9C7"; c.fillRect(0, 0, 22, 26);
    window.OfficeArt.person(c, 11, 25, Object.assign({ pose: "idle", facing: "f" }, window.OfficeArt.lookFor(m.id, m.status)), 0);
  }
  function trustPips(m) {
    const w = el("span", "pips" + (m.status === "certified" && m.score < 0.5 ? " warn" : ""));
    const n = m.status === "certified" ? Math.max(1, Math.round(m.score * 5)) : 0;
    for (let i = 0; i < 5; i++) w.append(el("i", i < n ? "on" : ""));
    return w;
  }
  function trustText(m) {
    if (m.status === "flagged") return null;
    if (m.status !== "certified") return "Not tested yet";
    const ev = /^(\d+)\/(\d+)/.exec(m.evidence || "");
    return "Trust " + Math.round(m.score * 100) + (ev ? ", passed " + ev[1] + " of " + ev[2] + " tests" : "");
  }
  function drawHire() {
    const ul = $("hire"); ul.replaceChildren();
    if (!S.market.length) { ul.append(el("li", "empty", "Nobody is for hire yet. Run \"bridge seed\" to add the demo helpers.")); return; }
    S.market.forEach((m) => {
      const li = el("li"); li.setAttribute("aria-current", String(selected === m.key));
      const b = el("button", "hirebtn"); b.type = "button";
      const cv = el("canvas"); cv.width = 22; cv.height = 26; cv.style.width = "44px"; cv.style.height = "52px"; portrait(cv, m);
      const who = el("span", "who"), nm = el("span", "name", window.niceName(m.id)); nm.append(el("span", "ver", "v" + m.version));
      who.append(nm, el("span", "blurb", m.summary));
      const tr = el("div", "trust");
      if (m.status === "flagged") {
        const reasons = [...new Set(m.violations.filter((v) => v !== "KILLED").map((v) => BAD[v] || v))];
        const t = el("span", "tag bad", "Caught cheating"); tr.append(t); who.append(tr, el("span", "blurb", "Our inspectors saw it " + reasons.join(", and ") + "."));
      } else {
        tr.append(trustPips(m), el("span", null, trustText(m)));
        if (m.status === "certified") tr.append(el("span", "tag good", "#" + m.rank));
        who.append(tr);
      }
      b.append(cv, who, el("span", "price", cents(priceOf(m))));
      b.onclick = () => choose(m.key);
      li.append(b);
      const fan = el("button", "fan", "♥ " + m.stars + " fans"); fan.type = "button"; fan.setAttribute("aria-label", "Become a fan of " + window.niceName(m.id));
      fan.onclick = async () => { try { const r = await api("/api/star", { key: m.key, user: "you" }); m.stars = r.stars; drawHire(); } catch (e) { say(e.message); } };
      li.append(fan); ul.append(li);
    });
  }
  function agentInfo(m) { return m ? { id: m.id, name: window.niceName(m.id), status: m.status } : null; }
  function choose(key) {
    selected = key; const m = S.market.find((x) => x.key === key); drawHire();
    const go = $("go"); go.disabled = running;
    go.textContent = m.status === "flagged" ? "Watch it get caught (up to " + cents(priceOf(m)) + ")" : "Start the job (up to " + cents(priceOf(m)) + ")";
    office.showIdle(agentInfo(m));
    caption(m.status === "flagged" ? window.niceName(m.id) + " was caught cheating. Run it to watch the guard stop it." : "You picked " + window.niceName(m.id) + ". Choose what it may look at, then press Start.");
    $("story").replaceChildren(); $("replay").textContent = "";
  }

  /* ---------- captions and the story list ---------- */
  function caption(t) { $("caption").textContent = t; $("floor").setAttribute("aria-label", t); }
  function story(t, cls) { const li = el("li", cls || "", t); $("story").append(li); $("story").scrollTop = $("story").scrollHeight; }
  function say(t) { caption(t); }

  /* ---------- the right-hand desk ---------- */
  function badge(kind) { return el("span", "badge " + kind); }
  function setStatus(kind, text) { const s = $("jobstatus"); s.replaceChildren(); const r = el("div", "status"); r.append(badge(kind), el("span", null, text)); s.append(r); }

  function showReport(rep) {
    const box = $("report"); box.replaceChildren();
    if (rep.outcome === "COMPLETE") {
      setStatus("success", "Done: the report passed inspection");
      const r = el("div", "report"); r.append(el("div", "reportbig", rep.result.summary), el("div", "muted small", "How worried to be: " + rep.result.risk));
      box.append(r, el("p", "muted small", "The guard checked this report before it reached you."));
    } else if (rep.outcome === "KILLED") {
      setStatus("blocked", "Stopped: nothing was delivered");
      box.append(el("p", null, "The helper was caught trying to take something it was not given. Its report was thrown away and your real files were never exposed."));
    } else if (rep.outcome === "FAILED_INFRA") {
      setStatus("blocked", "The Brain was busy");
      box.append(el("p", null, "The thinking service did not answer, so the job could not finish. You are not charged, and the helper is not blamed. Try again in a moment."));
    } else {
      setStatus("blocked", "No usable report");
      box.append(el("p", null, "The helper did not produce a report we could trust. You are not charged for it."));
    }
    const dl = el("dl", "kv"), add = (k, v) => { dl.append(el("dt", null, k), el("dd", null, v)); };
    add("Files it saw", rep.records_handed.length ? rep.records_handed.map((id) => fileName(id)).join(", ") : "none");
    add("Files kept locked", rep.withheld.length ? String(rep.withheld.length) : "none");
    box.append(dl);
    const det = el("details"); det.append(el("summary", null, "Tamper-proof record of this job (" + rep.journal_entries + " notes, all intact)"));
    (rep.journal || []).forEach((e) => { const r = el("div", "arow"); r.append(el("span", "muted", "#" + e.seq), el("span", null, (NOTE[e.kind] || e.kind) + (e.data && e.data.step ? ": " + e.data.step : ""))); det.append(r); });
    box.append(det);
    if (rep.outcome === "COMPLETE" && rep.proposals && rep.proposals.length) {
      const undo = el("button", "btn", "Undo everything from this job"); undo.type = "button"; undo.style.marginTop = "8px";
      undo.onclick = async () => { try { const r = await api("/api/revert", { run_id: rep.run_id }); undo.textContent = "Undone (" + r.removed_from_vault + " saved, " + r.dropped_pending + " waiting removed)"; undo.disabled = true; await refresh(); } catch (e) { undo.textContent = e.message; } };
      box.append(undo);
    }
  }
  function fileName(id) { const r = S.vault.find((x) => x.id === id); return r ? typeLabel(r.type).replace(/s$/, "") + " " + id : id; }

  function showCoins(rep) {
    const box = $("coinsbox"); box.replaceChildren(); const p = rep.payment; if (!p) return;
    const row = (k, v) => { const r = el("div", "row"); r.append(el("span", null, k), el("b", null, v)); box.append(r); };
    if (p.state === "DISPUTE_UPHELD" || p.state === "VOIDED") row("Hold released, back to you", cents(p.price));
    else row("Held for this job", cents(p.price));
    const taken = p.captured + p.refunded, dep = Math.min(p.floor, taken);
    if (dep > 0) row("Deposit paid", cents(dep));
    if (taken > p.floor) row("Paid for the report", cents(taken - p.floor));
    if (p.refunded > 0) row("Given back to you", cents(p.refunded));
    const note = el("p", "small"); note.style.marginTop = "8px";
    if (p.state === "RESULT_READY") {
      note.textContent = "The deposit is paid. Say the report is good to pay the rest, or say it is not what you wanted to pay only the deposit. If you do nothing it counts as good on " + new Date(p.accept_by * 1000).toLocaleDateString() + ".";
      box.append(note);
      const a = el("div", "acts"), ok = el("button", "btn", "Good: pay in full"), no = el("button", "btn warn", "Not what I wanted"); ok.type = no.type = "button";
      const decide = async (action) => { ok.disabled = no.disabled = true; try { rep.payment = await api("/api/settle", { run_id: rep.run_id, action }); showCoins(rep); await office.settle(rep.payment, true, story); await refresh(); } catch (e) { note.textContent = e.message + " Reload the page if this keeps happening."; ok.disabled = no.disabled = false; } };
      ok.onclick = () => decide("accept"); no.onclick = () => decide("reject"); a.append(ok, no); box.append(a);
    } else {
      note.textContent = p.state === "SETTLED" ? "All paid. The helper gets " + cents(p.payout.amount) + " after a 10% fee. This demo pays out instantly; a real marketplace would hold the money for days."
        : p.state === "SETTLED_REJECTED" ? "You only paid the deposit and the rest of the hold was released. The helper gets " + cents(p.payout.amount) + "."
        : p.state === "DISPUTE_HOLD" ? "The money is on hold until someone checks the complaint."
        : p.state === "DISPUTE_UPHELD" ? "Our inspectors had already caught this helper doing the same thing, so you got everything back and the helper earns nothing."
        : p.state === "VOIDED" ? "You were not charged. The hold was released because there was no usable report." : p.state;
      box.append(note);
    }
  }

  function drawNotes() {
    const box = $("notes"); box.replaceChildren();
    if (!S.proposals.length) { box.append(el("div", "empty", "Nothing yet. After a job a helper may suggest something worth remembering. It is saved only if you say yes.")); return; }
    S.proposals.forEach((p) => {
      const n = el("div", "note"); n.append(el("div", null, "“" + p.text + "”"), el("div", "muted small", "A helper suggests you remember this."));
      const a = el("div", "acts"), ok = el("button", "btn", "Remember it"), no = el("button", "btn", "No thanks"); ok.type = no.type = "button";
      ok.onclick = async () => { try { await api("/api/proposal", { id: p.id, action: "accept" }); await refresh(); } catch (e) { n.append(el("div", "muted small", e.message)); } };
      no.onclick = async () => { try { await api("/api/proposal", { id: p.id, action: "reject" }); await refresh(); } catch (e) { n.append(el("div", "muted small", e.message)); } };
      a.append(ok, no); n.append(a); box.append(n);
    });
  }

  function drawHistory() {
    const box = $("history"); box.replaceChildren();
    if (!S.history.length) { box.append(el("div", "empty", "No jobs yet. Your first one will show up here.")); return; }
    S.history.forEach((h) => {
      const c = el("div", "hist"); c.tabIndex = 0; c.setAttribute("role", "button");
      const tag = h.outcome === "COMPLETE" ? ["good", "done"] : h.outcome === "KILLED" ? ["bad", "stopped"] : ["wait", "no report"];
      c.append(el("div", null, h.pack.replace(/^[a-z-]+/, (m) => window.niceName(m)) + " "), el("span", "tag " + tag[0], tag[1]), el("div", "muted small", plain(h.summary)));
      const open = async () => {
        if (running) return;
        try { const rep = await api("/api/report/" + h.run_id); lastRep = rep; $("story").replaceChildren(); showAll(rep); await office.play(rep, { animate: false, records: records(), log: story, caption }); }
        catch (e) { say("That job is no longer available. Jobs are kept until the console restarts."); }
      };
      c.onclick = open; c.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } };
      box.append(c);
    });
  }
  function plain(s) { return String(s || "").replace(/Stopped for ([A-Z_]+);/, (m, k) => "Stopped because the helper " + (BAD[k] || k.toLowerCase().replace(/_/g, " ")) + ";").replace(/record\(s\)/g, "files").replace(/stayed private/g, "stayed locked"); }
  function records() { return new Map(S.vault.map((r) => [r.id, { type: r.type, sensitivity: r.sensitivity }])); }
  function showAll(rep) { showReport(rep); showCoins(rep); }

  function drawCoins() {
    const w = S.payments; if (!w) return;
    $("coinchip").textContent = "Paid to helpers " + cents(w.paid_out) + ", on hold " + cents(w.held);
    $("coinlabel").textContent = w.provider === "paypal-sandbox" ? "PayPal test coins" : "Test coins";
  }

  async function refresh() { S = await api("/api/state"); drawCoins(); drawLens(true); drawHire(); drawNotes(); drawHistory(); }

  /* ---------- running a job ---------- */
  function waitForApproval(pending) {
    return new Promise((resolve) => {
      const box = $("coinsbox"); box.replaceChildren();
      box.append(el("p", null, "Before the helper starts, approve a hold of " + cents(pending.price) + " on the payment page. Nothing is charged until there is a report."));
      const acts = el("div", "acts");
      if (/^https:\/\//.test(pending.approve_url)) { const a = document.createElement("a"); a.href = pending.approve_url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "btn"; a.textContent = "Open the approval page"; acts.append(a); }
      const go = el("button", "btn", "I approved, continue"); go.type = "button"; const msg = el("p", "muted small");
      go.onclick = async () => { go.disabled = true; msg.textContent = "Checking with the payment provider."; try { resolve(await api("/api/run/continue", { run_id: pending.run_id })); } catch (e) { msg.textContent = e.message + " Approve the hold on the payment page, then try again."; go.disabled = false; } };
      acts.append(go); box.append(acts, msg);
    });
  }

  async function start() {
    if (running || !selected) return;
    running = true; const go = $("go"); go.disabled = true; go.textContent = "Working...";
    $("story").replaceChildren(); $("report").replaceChildren(); $("coinsbox").replaceChildren(); $("replay").textContent = "";
    setStatus("thinking", "The helper is on the job"); caption("Hiring... one moment.");
    try {
      let rep = await api("/api/run", { key: selected, types: types(), max_sensitivity: level(), model: $("theft").checked ? "leak" : "nebius" });
      if (rep.needs_approval) rep = await waitForApproval(rep);
      lastRep = rep; $("replay").textContent = "The picture replays what really happened, taken from the job's tamper-proof record.";
      await office.play(rep, { animate: true, records: records(), log: story, caption });
      showAll(rep);
    } catch (e) {
      setStatus("blocked", "The job could not start");
      $("report").replaceChildren(el("p", null, e.message + " Check that you left at least one drawer open, then try again."));
    }
    try { await refresh(); } catch (e) { /* what happened is already on screen */ }
    running = false; go.disabled = false; const m = S && S.market.find((x) => x.key === selected); go.textContent = m ? "Hire again" : "Pick someone to hire first";
  }

  /* ---------- the assistant ---------- */
  function assistantSay(text, speak) {
    $("assistantsay").textContent = text; office.say("clerk", text, 7000);
    if (speak && "speechSynthesis" in window) { try { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } catch (e) { /* speaking is optional */ } }
  }
  function ask(text, spoken) {
    if (!text.trim()) return;
    const w = S.payments || {}, sees = $("count").textContent;
    const r = window.parseIntent(text, S.market, { selected, wallet: { captured: w.captured || 0, paid_out: w.paid_out || 0, held: w.held || 0 }, sees });
    if (r.action === "select") choose(r.agentKey);
    if (r.action === "confirm" && selected) $("go").focus();
    assistantSay(r.say, spoken || voiceOn);
  }
  function setupVoice() {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $("mic");
    if (!Rec) { mic.hidden = true; return; }
    recognition = new Rec(); recognition.lang = "en-US"; recognition.interimResults = false;
    recognition.onresult = (e) => { const t = e.results[0][0].transcript; $("ask").value = t; voiceOn = true; ask(t, true); };
    recognition.onend = () => { mic.classList.remove("on"); mic.setAttribute("aria-pressed", "false"); };
    recognition.onerror = () => { mic.classList.remove("on"); assistantSay("I could not hear you. You can type instead.", false); };
    mic.onclick = () => { try { recognition.start(); mic.classList.add("on"); mic.setAttribute("aria-pressed", "true"); } catch (e) { /* already listening */ } };
  }

  /* ---------- start up ---------- */
  async function init() {
    office = new window.Office($("floor"), { onDrawer: toggleType });
    try {
      S = await api("/api/state");
      drawCoins(); drawLens(false); drawHire(); drawNotes(); drawHistory();
      caption("Welcome! Pick someone to hire, choose what they may look at, then press Start.");
      $("go").onclick = start;
      document.querySelectorAll("#privacy input").forEach((i) => (i.onchange = lensChanged));
      $("askform").onsubmit = (e) => { e.preventDefault(); voiceOn = false; ask($("ask").value, false); $("ask").select(); };
      setupVoice();
      const logo = $("logo"); const c = logo.getContext("2d"); c.imageSmoothingEnabled = false; c.fillStyle = "#FFF8E7"; c.fillRect(0, 0, 20, 14);
      window.OfficeArt.person(c, 10, 14, { pose: "idle", facing: "f", shirt: "#5CA97A", hat: "cap", skin: "#E0AC82", hair: "#1A1320" }, 0);
    } catch (e) {
      $("hire").replaceChildren(el("li", "empty", "The console could not load: " + e.message + " Make sure \"bridge serve\" is still running, then reload this page."));
    }
  }
  init();
})();
