/* My helpers: build, test, publish and manage your own helpers. The harness (the steps a helper runs) is drawn as a graph you
   can touch: drag steps, draw arrows from one step to the next, click a step to change it. The server checks every change and
   says in plain words what is wrong. Strings from the server are inserted with textContent only. */
(function () {
  "use strict";
  let B = null, list = null, H = null, wf = null, sel = null, dirty = false, saveTimer = null, pollTimer = null, layout = {}, tab = "steps";
  let problems = [], showData = true, lastTry = null, pulse = [], view = { k: 1, x: 10, y: 10 }, fitNext = true, gsize = { w: 0, h: 0 };
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const btn = (text, cls, fn) => { const b = el("button", cls || "btn", text); b.type = "button"; if (fn) b.onclick = fn; return b; };
  const NS = "http://www.w3.org/2000/svg";
  const sv = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (text !== undefined) e.textContent = text; return e; };
  const note = (t) => { $("studionote").textContent = ""; if (t) B.toast(t, !/^(Published|Saved)/.test(t)); };
  const NW = 190, NH = 74, GX = 80, GY = 40;

  const KIND = {
    memory_search: { title: "Look through your files", fill: "#D2E7DA", hint: "Reads files from the shelves the person opened. Nothing else." },
    web_search: { title: "Look up the web", fill: "#F3DACA", hint: "Searches public pages. It can never be given your files." },
    llm: { title: "Think", fill: "#CFE5E9", hint: "Asks the thinking service to write something from what it was given." },
    gate: { title: "Check the answer", fill: "#F3E4BC", hint: "Stops a bad answer before it goes on." },
    code: { title: "Run a small program", fill: "#E0DAF2", hint: "Runs your own code in a sealed room with no internet." },
    return: { title: "Hand over the answer", fill: "#F3D3CD", hint: "The guard inspects this before it reaches the person." }
  };
  const kindOf = (s) => (s.kind === "tool" ? s.tool : s.kind);
  const steps = () => (wf && Array.isArray(wf.steps) ? wf.steps : []);
  const byId = (id) => steps().find((s) => s.id === id);

  /* ---------- screens ---------- */
  async function show() {
    try { list = await B.api("/api/studio"); } catch (e) { note(e.message); return; }
    drawList();
    if (!H && list.helpers.length) await openHelper(list.helpers[0].id);
    else if (!list.helpers.length) { H = null; drawEmpty(); }
  }

  function drawEmpty() {
    $("studiomain").hidden = true; $("studioempty").hidden = false;
  }

  function drawList() {
    const box = $("helperlist"); box.replaceChildren();
    list.helpers.forEach((h) => {
      const b = el("button", "threadbtn" + (H && H.id === h.id ? " cur" : "")); b.type = "button";
      const live = h.versions.find((v) => !v.revoked);
      b.append(el("span", "name", h.title), el("span", "blurb", h.problems ? window.plural(h.problems, "thing") + " to fix" : live ? "On the market: v" + live.version : "Draft v" + h.version));
      b.onclick = () => openHelper(h.id);
      box.append(b);
    });
    if (!list.helpers.length) box.append(el("p", "empty", "You have not built a helper yet."));
    const t = $("newtemplate"); t.replaceChildren();
    list.templates.forEach((x) => { const o = document.createElement("option"); o.value = x.id; o.textContent = x.title; t.append(o); });
  }

  async function createHelper(ev) {
    ev.preventDefault();
    try {
      const h = await B.api("/api/studio/create", { id: $("newname").value.trim().toLowerCase().replace(/\s+/g, "-"), template: $("newtemplate").value });
      $("newname").value = ""; note(""); list = await B.api("/api/studio"); H = null; await openHelper(h.id);
    } catch (e) { note(e.message); }
  }

  async function openHelper(id) {
    try { H = await B.api("/api/studio/helper?id=" + encodeURIComponent(id)); } catch (e) { note(e.message); return; }
    fitNext = true; wf = H.workflow ? JSON.parse(JSON.stringify(H.workflow)) : null; layout = H.layout || {}; problems = H.problems; sel = null; lastTry = null; pulse = []; dirty = false;
    $("studiomain").hidden = false; $("studioempty").hidden = true; note("");
    drawList(); draw(); watchTests();
  }

  function draw() {
    $("helpertitle").textContent = (H.id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())) + "  ·  version " + (H.manifest.version || "?");
    drawProblems(); drawGraph(); drawPanel();
  }

  const nameOf = (id) => { const s = byId(id); return s ? (KIND[kindOf(s)] || {}).title + " (" + id + ")" : id; };
  function say(p) {  // the checker's words, in plain language, and which step they are about
    let m;
    if ((m = /step '([a-z0-9_]+)' is unreachable from start/.exec(p))) return [m[1], "“" + nameOf(m[1]) + "” is not connected: nothing leads to it. Drag the green dot of an earlier step onto it, or remove it."];
    if ((m = /step '([a-z0-9_]+)': (.*)/.exec(p))) return [m[1], "“" + nameOf(m[1]) + "”: " + m[2].replace(/`/g, "").replace(/'([a-z0-9_]+)'/g, (x, id) => (byId(id) ? "“" + nameOf(id) + "”" : x)).replace("which never runs before it", "which only runs later. Move it after that step, or untick it below.")];
    if ((m = /cycle through step '([a-z0-9_]+)'/.exec(p))) return [m[1], "The steps go round in a circle at “" + nameOf(m[1]) + "”. Loops are not available yet."];
    return [null, p.replace(/^The steps: /, "")];
  }
  function drawProblems() {
    const box = $("problems"); box.replaceChildren();
    if (!problems.length) { box.append(el("p", "small okline", dirty ? "Saving…" : "✓ Everything checks out. This helper is ready to practise or publish.")); return; }
    box.append(el("p", "small warnline", window.plural(problems.length, "thing") + " to fix before it can be published:"));
    const ul = el("ul", "small probs");
    problems.slice(0, 6).forEach((p) => {
      const [id, text] = say(p), li = el("li");
      if (id && byId(id)) { const b = btn(text, "linkbtn probbtn", () => select(id)); b.title = "Show this step"; li.append(b); } else li.append(text);
      ul.append(li);
    });
    box.append(ul);
  }

  /* ---------- saving ---------- */
  function changed(what) {
    dirty = true; drawProblems();
    clearTimeout(saveTimer); saveTimer = setTimeout(() => save(what), 500);
  }
  async function save(what) {
    if (!H) return;
    const body = { id: H.id, layout };
    if (!what || what.includes("steps")) body.workflow = wf;
    if (!what || what.includes("about")) body.manifest = H.manifest;
    try {
      const r = await B.api("/api/studio/save", body);
      dirty = false; problems = r.problems; H.caps = r.caps; H.versions = r.versions;
      drawProblems(); if (tab === "publish") drawPanel();
    } catch (e) { note(e.message); }
  }

  /* ---------- the graph ---------- */
  function depths() {
    const d = {}, order = [], s0 = wf && wf.start;
    if (!s0 || !byId(s0)) return { d, order };
    d[s0] = 0; order.push(s0);
    for (const id of order) { const s = byId(id); [s.next, s.on_fail].forEach((t) => { if (t && byId(t) && !(t in d)) { d[t] = d[id] + 1; order.push(t); } }); }
    for (let i = 0; i < steps().length; i++) for (const id of order) { const s = byId(id); [s.next, s.on_fail].forEach((t) => { if (t && byId(t) && d[t] <= d[id] && !(d[t] > steps().length)) d[t] = d[id] + 1; }); }
    steps().forEach((s) => { if (!(s.id in d)) { d[s.id] = 0; order.push(s.id); } });  // steps nothing leads to still appear
    return { d, order };
  }
  function privateSet() {
    const p = new Set(steps().filter((s) => s.memory === "lens").map((s) => s.id)); p.add("history");
    let ch = true; while (ch) { ch = false; steps().forEach((s) => { if (!p.has(s.id) && (s.reads || []).some((r) => p.has(r))) { p.add(s.id); ch = true; } }); }
    return p;
  }
  function pos(s, i, lanes) {
    if (layout[s.id]) return layout[s.id];
    return { x: 150 + lanes.col * (NW + GX), y: 40 + lanes.row * (NH + GY) };
  }
  function place() {
    const { d, order } = depths(), rows = {}, out = {};
    order.forEach((id, i) => { const c = d[id]; rows[c] = (rows[c] === undefined ? -1 : rows[c]) + 1; out[id] = pos(byId(id), i, { col: c, row: rows[c] }); });
    return out;
  }
  const fail = (id) => problems.some((p) => new RegExp("step '" + id + "'").test(p));

  function drawGraph() {
    const svg = $("graph"); svg.replaceChildren();
    if (!wf || !steps().length) { svg.append(sv("text", { x: 20, y: 40, fill: "#6B5878" }, "The steps could not be read. Fix the text under “Edit as text”, or start again from a template.")); return; }
    const P = place(), priv = privateSet();
    P.task = { x: 14, y: 30 }; P.history = { x: 14, y: 130 };
    const defs = sv("defs");
    [["arr", "#1A1320"], ["arrfail", "#D96A62"], ["arrdata", "#A899B5"]].forEach(([id, col]) => {
      const m = sv("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
      m.append(sv("path", { d: "M0,0 L10,5 L0,10 z", fill: col })); defs.append(m);
    });
    svg.append(defs);
    const shadow = sv("filter", { id: "gsoft", x: "-20%", y: "-20%", width: "140%", height: "150%" }); shadow.append(sv("feDropShadow", { dx: 0, dy: 3, stdDeviation: 3.5, "flood-color": "#3D2E4A", "flood-opacity": 0.22 })); defs.append(shadow);
    const vp = sv("g", { id: "gvp" }); svg.append(vp);
    const edges = sv("g"), nodes = sv("g"); vp.append(edges, nodes);
    let w = 600, h = 300; Object.values(P).forEach((p) => { w = Math.max(w, p.x + NW + 40); h = Math.max(h, p.y + NH + 40); }); gsize = { w, h };

    const inputs = [["task", "Your message"], ["history", "Chat so far"]];
    inputs.forEach(([id, label]) => {
      const p = P[id], g = sv("g", { class: "pill" }); g.append(sv("rect", { x: p.x, y: p.y, width: 104, height: 26, rx: 13, fill: id === "history" ? "#FFF8E7" : "#CFE5E9", stroke: "#1A1320", "stroke-width": 2 }), sv("text", { x: p.x + 52, y: p.y + 17, "text-anchor": "middle", "font-size": 11 }, label));
      nodes.append(g);
    });
    const edge = (a, b, cls, marker, dy) => {
      const A = P[a], T = P[b]; if (!A || !T) return;
      const fromInput = a === "task" || a === "history";
      const x1 = fromInput ? A.x + 104 : A.x + NW, y1 = fromInput ? A.y + 13 : A.y + (cls === "fail" ? NH : NH / 2);
      const x2 = T.x, y2 = T.y + NH / 2 + (dy || 0), off = Math.max(40, Math.abs(x2 - x1) / 2);
      const path = sv("path", { d: "M" + x1 + "," + y1 + " C" + (x1 + off) + "," + (cls === "fail" ? y1 + 50 : y1) + " " + (x2 - off) + "," + y2 + " " + x2 + "," + y2, class: "edge " + cls, "marker-end": "url(#" + marker + ")", fill: "none" });
      edges.append(path);
    };
    steps().forEach((s) => {
      if (s.next) edge(s.id, s.next, "next", "arr");
      if (s.on_fail) edge(s.id, s.on_fail, "fail", "arrfail");
      if (showData) (s.reads || []).forEach((r, i) => { if (byId(r) || r === "task" || r === "history") edge(r, s.id, "data", "arrdata", -14 + i * 7); });
    });

    steps().forEach((s) => {
      const p = P[s.id], k = KIND[kindOf(s)] || { title: kindOf(s), fill: "#F4E9C7" };
      const g = sv("g", { class: "node" + (sel === s.id ? " sel" : "") + (fail(s.id) ? " bad" : "") + (pulse.includes(s.id) ? " pulse" : ""), tabindex: 0, role: "button", "aria-label": k.title + " (" + s.id + ")" + (priv.has(s.id) ? ", holds private data" : "") });
      g.setAttribute("transform", "translate(" + p.x + "," + p.y + ")");
      g.append(sv("title", {}, k.hint));
      g.append(sv("rect", { width: NW, height: NH, rx: 16, fill: k.fill, stroke: "#1A1320", "stroke-width": sel === s.id ? 3.5 : 2, filter: "url(#gsoft)" }));
      g.append(sv("text", { x: 14, y: 27, "font-size": 14, "font-weight": 700 }, k.title));
      g.append(sv("text", { x: 14, y: 46, "font-size": 11.5, fill: "#3D2E4A" }, s.id));
      if (priv.has(s.id) && s.kind !== "return") g.append(sv("text", { x: 14, y: 63, "font-size": 10.5, fill: "#9a3a33" }, "🔒 holds your private data"));
      else if (s.tool === "web_search") g.append(sv("text", { x: 14, y: 63, "font-size": 10.5, fill: "#6B5878" }, "public"));
      if (s.kind !== "return") {
        const out = sv("circle", { cx: NW, cy: NH / 2, r: 7, fill: "#5CA97A", stroke: "#1A1320", "stroke-width": 2, class: "port" }); out.append(sv("title", {}, "Drag to the next step"));
        out.addEventListener("pointerdown", (e) => startLink(e, s.id, "next")); g.append(out);
        if (s.kind === "gate") { const f = sv("circle", { cx: NW / 2, cy: NH, r: 7, fill: "#D96A62", stroke: "#1A1320", "stroke-width": 2, class: "port" }); f.append(sv("title", {}, "Drag to where it goes if the check fails")); f.addEventListener("pointerdown", (e) => startLink(e, s.id, "on_fail")); g.append(f); }
      }
      g.addEventListener("pointerdown", (e) => startDrag(e, s.id));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(s.id); } });
      nodes.append(g);
    });
    if (fitNext) { fitNext = false; fitGraph(); requestAnimationFrame(fitGraph); setTimeout(fitGraph, 250); } else applyGraphView();
  }

  /* zoom and move, like a map */
  function applyGraphView() { const vp = $("gvp"); if (vp) vp.setAttribute("transform", "translate(" + view.x + " " + view.y + ") scale(" + view.k + ")"); }
  function fitGraph() {
    const r = $("graph").getBoundingClientRect(); if (!r.width || !gsize.w) return;
    const k = Math.min((r.width - 20) / gsize.w, (r.height - 20) / gsize.h, 1.1);
    view = { k, x: Math.max(10, (r.width - gsize.w * k) / 2), y: 10 }; applyGraphView();
  }
  function zoomGraph(f, px, py) {
    const k2 = Math.min(2.5, Math.max(0.3, view.k * f)), q = k2 / view.k;
    view = { k: k2, x: px - (px - view.x) * q, y: py - (py - view.y) * q }; applyGraphView();
  }
  function setupGraphView() {
    const svg = $("graph");
    svg.addEventListener("wheel", (e) => { e.preventDefault(); const r = svg.getBoundingClientRect(); zoomGraph(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); }, { passive: false });
    svg.addEventListener("pointerdown", (e) => {
      if (e.target.closest && e.target.closest(".node,.pill")) return;
      const sx = e.clientX, sy = e.clientY, ox = view.x, oy = view.y; svg.style.cursor = "grabbing";
      const move = (ev) => { view.x = ox + ev.clientX - sx; view.y = oy + ev.clientY - sy; applyGraphView(); };
      const up = () => { svg.style.cursor = ""; window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
    });
    const mid = () => { const r = svg.getBoundingClientRect(); return [r.width / 2, r.height / 2]; };
    $("gzoomin").onclick = () => zoomGraph(1.25, ...mid()); $("gzoomout").onclick = () => zoomGraph(1 / 1.25, ...mid()); $("gfit").onclick = fitGraph;
  }

  const svgPoint = (e) => { const r = $("graph").getBoundingClientRect(); return { x: (e.clientX - r.left - view.x) / view.k, y: (e.clientY - r.top - view.y) / view.k }; };

  function startDrag(e, id) {
    if (e.target.classList && e.target.classList.contains("port")) return;
    e.preventDefault(); const P = place(), p0 = svgPoint(e), o = { x: P[id].x, y: P[id].y }; let moved = false;
    const move = (ev) => { const q = svgPoint(ev); if (Math.abs(q.x - p0.x) + Math.abs(q.y - p0.y) > 4) moved = true; if (moved) { layout[id] = { x: Math.max(0, Math.round(o.x + q.x - p0.x)), y: Math.max(0, Math.round(o.y + q.y - p0.y)) }; drawGraph(); } };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); if (moved) changed(["layout"]); else select(id); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }

  function startLink(e, from, kind) {
    e.preventDefault(); e.stopPropagation();
    const svg = $("graph"), P = place(), a = P[from], x1 = kind === "next" ? a.x + NW : a.x + NW / 2, y1 = kind === "next" ? a.y + NH / 2 : a.y + NH;
    const line = sv("line", { x1, y1, x2: x1, y2: y1, stroke: kind === "next" ? "#5CA97A" : "#D96A62", "stroke-width": 3, "stroke-dasharray": "6 4" }); ($("gvp") || svg).append(line);
    const move = (ev) => { const q = svgPoint(ev); line.setAttribute("x2", q.x); line.setAttribute("y2", q.y); };
    const up = (ev) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); line.remove();
      const q = svgPoint(ev), hit = steps().find((s) => s.id !== from && P[s.id] && q.x >= P[s.id].x && q.x <= P[s.id].x + NW && q.y >= P[s.id].y && q.y <= P[s.id].y + NH);
      if (hit) { byId(from)[kind] = hit.id; changed(["steps"]); drawGraph(); if (sel === from) drawPanel(); }
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }

  function select(id) { sel = id; tab = "steps"; drawGraph(); drawPanel(); }

  /* ---------- adding and removing steps ---------- */
  function newId(base) { let i = 1; while (byId(base + (i > 1 ? i : ""))) i++; return base + (i > 1 ? i : ""); }
  function mainPath() { const seen = new Set(), order = []; let cur = wf && wf.start; while (cur && byId(cur) && !seen.has(cur)) { seen.add(cur); order.push(byId(cur)); cur = byId(cur).next; } return order; }
  function lastOnMainPath() {  // the last working step before the check or the hand-over: new steps go after it
    return mainPath().filter((x) => x.kind !== "return" && x.kind !== "gate").pop() || null;
  }
  function addStep(kind) {
    if (!wf) return;
    const tmpl = {
      files: (id) => ({ id, kind: "tool", tool: "memory_search", tools: ["memory_search"], memory: "lens", prompt: "{task}" }),
      web: (id) => ({ id, kind: "tool", tool: "web_search", tools: ["web_search"], prompt: "{task}" }),
      think: (id) => ({ id, kind: "llm", reads: ["task", "history"], prompt: "Answer the question in INPUTS.task using only what is in the other inputs. Reply as JSON with the key summary: at most 3 plain sentences." }),
      check: (id) => ({ id, kind: "gate", check: "result_matches_schema", reads: [(steps().filter((s) => s.kind === "llm").pop() || {}).id].filter(Boolean) }),
      program: (id) => ({ id, kind: "code", script: "result = {\"summary\": \"ok\"}\n", reads: [] }),
      deliver: (id) => ({ id, kind: "return", reads: [(steps().filter((s) => s.kind === "llm").pop() || {}).id].filter(Boolean) })
    }[kind];
    const base = { files: "read", web: "web", think: "think", check: "check", program: "program", deliver: "done" }[kind];
    const s = tmpl(newId(base));
    if (kind === "files" || kind === "web") {  // something to read or look up goes before the step that thinks, and that step reads it
      const order = mainPath(), at = order.findIndex((x) => x.kind === "llm");
      if (at >= 0) {
        const target = order[at], prev = order[at - 1];
        if (prev) prev.next = s.id; else wf.start = s.id;
        s.next = target.id; target.reads = [...new Set([...(target.reads || []), s.id])];
        wf.steps.push(s); sel = s.id; fitNext = true; changed(["steps"]); drawGraph(); drawPanel(); return;
      }
    }
    const lastThink = mainPath().filter((x) => x.kind === "llm").pop();
    const after = kind === "check" ? (lastThink || (sel && byId(sel)) || lastOnMainPath()) : (sel && byId(sel)) || lastOnMainPath();
    if (after && after.kind !== "return" && s.kind !== "return") { s.next = after.next; if (s.kind === "gate") { const bad = steps().find((x) => x.kind === "return" && !(x.reads || []).length); s.on_fail = after.on_fail || (bad && bad.id) || undefined; } after.next = s.id; }
    if (kind === "deliver") {  // a new hand-over step is joined to the first check that has nowhere to go on failure
      const gate = steps().find((x) => x.kind === "gate" && !x.on_fail); if (gate) gate.on_fail = s.id;
    }
    else if (s.kind !== "return") { const last = steps().find((x) => x.kind === "return"); if (last) s.next = last.id; }
    wf.steps.push(s); if (!wf.start) wf.start = s.id;
    sel = s.id; fitNext = true; changed(["steps"]); drawGraph(); drawPanel();
  }
  function removeStep(id) {
    const s = byId(id); if (!s) return;
    wf.steps = wf.steps.filter((x) => x.id !== id);
    wf.steps.forEach((x) => { if (x.next === id) { if (s.next && s.next !== x.id) x.next = s.next; else delete x.next; } if (x.on_fail === id) delete x.on_fail; x.reads = (x.reads || []).filter((r) => r !== id); if (x.propose === id) delete x.propose; });
    if (wf.start === id) wf.start = s.next || (wf.steps[0] && wf.steps[0].id);
    delete layout[id]; sel = null; fitNext = true; changed(["steps"]); drawGraph(); drawPanel();
  }

  /* ---------- the right-hand panel ---------- */
  function drawPanel() {
    ["steps", "about", "try", "publish", "text"].forEach((t) => { const b = $("ptab-" + t); b.setAttribute("aria-selected", String(tab === t)); });
    const box = $("panelbody"); box.replaceChildren();
    ({ steps: stepPanel, about: aboutPanel, try: tryPanel, publish: publishPanel, text: textPanel })[tab](box);
  }
  function field(label, node, hint) { const w = el("label", "fld"); w.append(el("span", "small", label), node); if (hint) w.append(el("span", "small muted", hint)); return w; }
  function textarea(v, rows, fn) { const t = document.createElement("textarea"); t.rows = rows; t.value = v || ""; t.maxLength = 4000; t.oninput = () => fn(t.value); return t; }
  function input(v, fn, max) { const t = document.createElement("input"); t.type = "text"; t.value = v || ""; t.maxLength = max || 200; t.oninput = () => fn(t.value); return t; }

  function stepPanel(box) {
    const s = sel && byId(sel);
    if (!s) {
      box.append(el("p", "small", "Click a step in the picture to change it. Drag a step to move it. Drag the green dot of a step onto another step to say what comes next."));
      const legend = el("div", "legend"); Object.values(KIND).forEach((k) => { const r = el("div", "small"); const sw = el("i", "sw"); sw.style.background = k.fill; r.append(sw, k.title); legend.append(r); }); box.append(legend);
      box.append(el("p", "small muted", "🔒 means a step holds your private files, so it can never be connected to the web. The picture shows this, and the checker enforces it."));
      return;
    }
    const k = KIND[kindOf(s)] || { title: kindOf(s), hint: "" };
    box.append(el("h3", "sub", k.title), el("p", "small muted", k.hint), el("p", "small", "Step name: " + s.id));
    if (s.kind === "llm") box.append(field("What should it do? (instructions for the thinking service)", textarea(s.prompt, 7, (v) => { s.prompt = v; changed(["steps"]); })));
    if (s.kind === "tool" && s.tool === "memory_search") box.append(field("What to look for", input(s.prompt, (v) => { s.prompt = v; changed(["steps"]); }, 300), "{task} means the person's message."));
    if (s.kind === "tool" && s.tool === "web_search") box.append(field("What to search for", input(s.prompt, (v) => { s.prompt = v; changed(["steps"]); }, 300), "{task} means the person's message. Never put their files here."));
    if (s.kind === "code") box.append(field("The program (runs with no internet)", textarea(s.script, 8, (v) => { s.script = v; changed(["steps"]); }), "Leave the answer in a variable called result. Needs the sealed room to be available on this computer."));
    if (s.kind === "gate") box.append(el("p", "small", "Checks that the answer has exactly the fields you described under “About”. If it does not, the helper goes to the failure step."));
    if (s.kind !== "return") {
      const sn = document.createElement("select"); [["", "(nothing: it ends here)"]].concat(steps().filter((x) => x.id !== s.id).map((x) => [x.id, (KIND[kindOf(x)] || {}).title + " (" + x.id + ")"])).forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; sn.append(o); });
      sn.value = s.next || ""; sn.onchange = () => { if (sn.value) s.next = sn.value; else delete s.next; changed(["steps"]); drawGraph(); };
      box.append(field("What comes next", sn));
    }
    if (s.kind === "gate") {
      const fn = document.createElement("select"); [["", "(choose)"]].concat(steps().filter((x) => x.id !== s.id).map((x) => [x.id, (KIND[kindOf(x)] || {}).title + " (" + x.id + ")"])).forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; fn.append(o); });
      fn.value = s.on_fail || ""; fn.onchange = () => { if (fn.value) s.on_fail = fn.value; else delete s.on_fail; changed(["steps"]); drawGraph(); };
      box.append(field("If the check fails, go to", fn));
    }
    if (s.kind !== "tool") {
      const fs = el("fieldset", "reads"); fs.append(el("legend", "small", "What this step may read"));
      const opts = [["task", "Your message"], ["history", "The chat so far (private)"]].concat(steps().filter((x) => x.id !== s.id).map((x) => [x.id, (KIND[kindOf(x)] || {}).title + " (" + x.id + ")"]));
      opts.forEach(([v, t]) => { const l = el("label", "small"), c = document.createElement("input"); c.type = "checkbox"; c.checked = (s.reads || []).includes(v); c.onchange = () => { const set = new Set(s.reads || []); c.checked ? set.add(v) : set.delete(v); s.reads = [...set]; changed(["steps"]); drawGraph(); }; l.append(c, t); fs.append(l); });
      box.append(fs);
    }
    if (s.kind === "tool" && s.tool === "memory_search") box.append(el("p", "small muted", "It can only reach the shelves the person opens in their chat."));
    const acts = el("div", "acts"); acts.append(btn("Make this the first step", "btn", () => { wf.start = s.id; changed(["steps"]); drawGraph(); }), btn("Remove this step", "btn warn", (e) => { if (e.target.dataset.armed) removeStep(s.id); else { e.target.dataset.armed = "1"; e.target.textContent = "Really remove?"; setTimeout(() => { delete e.target.dataset.armed; e.target.textContent = "Remove this step"; }, 3500); } }));
    box.append(acts);
  }

  /* about: the description that people read before they hire */
  function aboutPanel(box) {
    const m = H.manifest;
    box.append(el("p", "small muted", "This is what people read before they hire your helper. Be concrete: the tests show whether it holds up."));
    box.append(field("One sentence about it", textarea(m.summary, 2, (v) => { m.summary = v; changed(["about"]); })));
    box.append(field("Best at", input(m.speciality, (v) => { m.speciality = v; changed(["about"]); }, 60)));
    box.append(field("Version", input(m.version, (v) => { m.version = v; changed(["about"]); }, 20), "Like 0.2.0. Raise the first number when it can do more than before."));
    const sel2 = document.createElement("select"); [["", "General (sales accounts)"]].concat(list.suites.map((s) => [s.id, s.title])).forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; sel2.append(o); });
    sel2.value = m.suite || ""; sel2.onchange = () => { if (sel2.value) m.suite = sel2.value; else delete m.suite; changed(["about"]); };
    box.append(field("It will be tested on", sel2, "The tester asks your helper these questions and checks its answers."));
    box.append(el("h3", "sub", "What it can do"));
    (m.skills = m.skills || []).forEach((s, i) => {
      const d = el("div", "skill");
      d.append(field("Skill name", input(s.name, (v) => { s.name = v; changed(["about"]); }, 60)), field("What it actually does", textarea(s.does, 2, (v) => { s.does = v; changed(["about"]); })),
        field("Example questions (one per line)", textarea((s.try_asking || []).join("\n"), 3, (v) => { s.try_asking = v.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 3); changed(["about"]); })));
      if (m.skills.length > 1) d.append(btn("Remove this skill", "linkbtn", () => { m.skills.splice(i, 1); changed(["about"]); drawPanel(); }));
      box.append(d);
    });
    if (m.skills.length < 5) box.append(btn("+ Add a skill", "btn", () => { m.skills.push({ name: "", does: "", try_asking: [] }); drawPanel(); }));
    box.append(el("h3", "sub", "What it cannot do"));
    box.append(field("Limits (one per line)", textarea((m.limits || []).join("\n"), 3, (v) => { m.limits = v.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5); changed(["about"]); })));
    resultEditor(box, m);
  }

  function resultEditor(box, m) {
    box.append(el("h3", "sub", "What its answer looks like"));
    const sch = m.result_schema || {}, props = sch.properties || {}, simple = Object.keys(props).every((k) => { const p = props[k]; return p.type === "string" || p.enum || (p.type === "array" && p.items && p.items.type === "string"); });
    if (!simple) { box.append(el("p", "small muted", "This answer shape is more detailed than this editor can show. Use “Edit as text” to change it.")); return; }
    box.append(el("p", "small muted", "Every answer has a summary. Add other fields if you need them; the checker rejects answers that do not match."));
    const rows = el("div", "fieldrows");
    const draw = () => {
      rows.replaceChildren();
      Object.keys(props).forEach((name) => {
        const p = props[name], r = el("div", "frow"); r.append(el("b", "small", name));
        const type = p.enum ? "choice" : p.type === "array" ? "list" : "text";
        r.append(el("span", "small muted", type === "choice" ? "one of: " + p.enum.join(", ") : type === "list" ? "a list" : "text"));
        if (name !== "summary") r.append(btn("Remove", "linkbtn", () => { delete props[name]; sch.required = (sch.required || []).filter((x) => x !== name); changed(["about"]); draw(); }));
        rows.append(r);
      });
    };
    draw(); box.append(rows);
    const nm = input("", () => {}, 30); nm.placeholder = "field name"; const ty = document.createElement("select");
    [["text", "text"], ["list", "a list of short lines"], ["choice", "one of a few words"]].forEach(([v, t]) => { const o = document.createElement("option"); o.value = v; o.textContent = t; ty.append(o); });
    const ch = input("", () => {}, 80); ch.placeholder = "low, medium, high"; ch.hidden = true; ty.onchange = () => { ch.hidden = ty.value !== "choice"; };
    box.append(el("div", "composerrow"), nm, ty, ch, btn("Add the field", "btn", () => {
      const name = nm.value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_"); if (!name || props[name]) return;
      props[name] = ty.value === "list" ? { type: "array", items: { type: "string", maxLength: 300 }, maxItems: 20 } : ty.value === "choice" ? { enum: ch.value.split(",").map((x) => x.trim()).filter(Boolean) } : { type: "string", maxLength: 600 };
      if (ty.value === "choice" && !props[name].enum.length) { delete props[name]; return; }
      sch.properties = props; m.result_schema = sch; nm.value = ""; changed(["about"]); draw();
    }));
  }

  /* try it */
  function tryPanel(box) {
    box.append(el("p", "small muted", "A practice run on your own files. Nothing is published and no coins move."));
    const q = textarea("", 2, () => {}); q.id = "tryq"; q.placeholder = "Ask it something, like a person would."; box.append(field("Your question", q));
    const fs = el("fieldset", "reads"); fs.append(el("legend", "small", "Shelves it may open"));
    (B.state().memory.shelves || []).filter((s) => s.depth <= 1).forEach((s) => { const l = el("label", "small"), c = document.createElement("input"); c.type = "checkbox"; c.value = s.path; l.append(c, "  ".repeat(s.depth) + s.name + " (" + s.count + ")"); fs.append(l); });
    box.append(fs);
    const out = el("div", "tryout"); out.id = "tryout";
    const go = btn("Run it", "btn go2", async () => {
      go.disabled = true; out.replaceChildren(el("p", "small muted", "Running…"));
      try {
        const r = await B.api("/api/studio/try", { id: H.id, task: q.value, shelves: [...fs.querySelectorAll("input:checked")].map((c) => c.value) });
        lastTry = r; showTry(out, r); await playPulse(r.visited);
      } catch (e) { out.replaceChildren(el("p", "warnline small", e.message)); }
      go.disabled = false;
    });
    box.append(go, out);
    if (lastTry) showTry(out, lastTry);
  }
  function showTry(out, r) {
    out.replaceChildren();
    out.append(el("div", "report", r.outcome === "COMPLETE" ? r.answer : r.outcome === "KILLED" ? "The guard stopped this helper. Nothing was delivered." : "No usable answer. " + (r.reasons[0] || "")));
    if (r.files.length) { const d = el("details"); d.append(el("summary", null, "It read " + r.files.length + " of your files")); r.files.forEach((f) => d.append(el("div", "small", f.shelf + ": " + f.text))); out.append(d); }
    else out.append(el("p", "small muted", "It read none of your files."));
    const how = el("details"); how.append(el("summary", null, "What it did")); r.how.forEach((t) => how.append(el("div", "small", "• " + t))); out.append(how);
  }
  async function playPulse(ids) { for (const id of ids) { pulse = [id]; drawGraph(); await new Promise((r) => setTimeout(r, 450)); } pulse = []; drawGraph(); }

  /* publish and manage */
  function chipFor(v) {
    if (v.revoked) return ["Retired", "wait"];
    if (v.testing) return ["Being tested…", "wait"];
    if (v.status === "flagged") return ["Caught cheating while tested", "bad"];
    if (v.status === "certified") return ["Trust " + v.score + " of 100 (" + v.passes + " of " + v.total + " tests)", "good"];
    return [v.test_error ? "Testing did not finish" : "Not tested yet", "wait"];
  }
  function publishPanel(box) {
    const m = H.manifest;
    box.append(el("p", "small", "Publishing puts version " + m.version + " on the market with your signature. A tester then runs it on a fixed set of questions and tries to catch it cheating. Its trust score comes from that, not from you."));
    if (problems.length) box.append(el("p", "small warnline", "Fix the " + window.plural(problems.length, "thing") + " listed at the top first."));
    const last = H.versions[0] || {}, mode = { v: last.plan || "flat" };
    const num = (v, step, min, max, label) => { const e = document.createElement("input"); e.type = "number"; e.step = step; e.min = min; e.max = max; e.value = v; e.setAttribute("aria-label", label); return e; };
    const f = {
      price: num(last.price_usd || 0.2, 0.05, 0.01, 5, "Price in dollars"), base: num(last.base_usd || 0.05, 0.01, 0, 5, "Starting price in dollars"),
      perFile: num(last.per_file_cents || 3, 1, 1, 500, "Cents for every file it reads"), perTok: num(last.per_1k_tokens_cents || 2, 1, 1, 500, "Cents for every 1,000 tokens"),
      light: num(last.light_cents || 10, 1, 1, 500, "Price of a light question in cents"), standard: num(last.standard_cents || 25, 1, 1, 500, "Price of a standard question in cents"),
      deep: num(last.deep_cents || 60, 1, 1, 500, "Price of a deep question in cents"), monthly: num(last.monthly_usd || 5, 0.5, 0.5, 50, "Monthly fee in dollars"),
      included: num(last.included_answers || 100, 1, 1, 1000, "Answers included each month")
    };
    const mail = input(last.payout_email || "", () => {}, 120); mail.placeholder = "you@example.com (optional)";
    const PLANS = [
      ["flat", "One price", "The same price for every answer. Simple and predictable."],
      ["per_file", "By files read", "A starting price plus a few cents for every file the helper reads, up to a maximum. Good when the work grows with the notes."],
      ["per_token", "By thinking used", "A starting price plus cents for every 1,000 tokens the model used, up to a maximum. Good when answers vary a lot in length."],
      ["complexity", "By how hard the question was", "One price for light, standard and deep questions. The platform decides which from what the run did, not from what the helper says."],
      ["monthly", "Monthly plan", "One fee for 30 days and a number of answers. It never renews by itself: the buyer approves each new month."]
    ];
    const pick = el("div", "plans");
    PLANS.forEach(([v, t, d]) => {
      const l = el("label", "plancard" + (mode.v === v ? " on" : "")), r = document.createElement("input"); r.type = "radio"; r.name = "pricemode"; r.value = v; r.checked = mode.v === v;
      r.onchange = () => { mode.v = v; pick.querySelectorAll(".plancard").forEach((c) => c.classList.toggle("on", c.firstChild.value === v)); drawFields(); };
      const body = el("div"); body.append(el("b", null, t), el("div", "small muted", d)); l.append(r, body); pick.append(l);
    });
    const fields = el("div"), preview = el("p", "small preview");
    const c = (x) => Math.round(parseFloat(x.value) * 100) || 0, n = (x) => parseInt(x.value, 10) || 0;
    const drawPreview = () => {
      const cap = c(f.price);
      preview.textContent = {
        flat: "Every answer costs " + cap + "¢.",
        per_file: "An answer that reads 4 files costs " + Math.min(cap, c(f.base) + 4 * n(f.perFile)) + "¢. The buyer sees the maximum (" + cap + "¢) before starting and pays only for what was read.",
        per_token: "An answer that uses 2,000 tokens costs " + Math.min(cap, c(f.base) + Math.ceil(2 * n(f.perTok))) + "¢. The buyer sees the maximum (" + cap + "¢) first and pays only for what was used.",
        complexity: "Light " + n(f.light) + "¢, standard " + n(f.standard) + "¢, deep " + n(f.deep) + "¢. Deep means it ran a program, thought three or more times, or read 12 or more files. Standard means it thought twice, searched the web, or read 4 or more files. The buyer sees the deepest price first.",
        monthly: "The buyer pays $" + (parseFloat(f.monthly.value) || 0).toFixed(2) + " once and can ask up to " + n(f.included) + " answers in 30 days. There is no automatic renewal."
      }[mode.v];
    };
    const drawFields = () => {
      fields.replaceChildren();
      const rows = {
        flat: [["Price per answer (US dollars)", f.price]],
        per_file: [["Starting price (US dollars)", f.base], ["Cents for every file it reads", f.perFile], ["Most one answer can cost (US dollars)", f.price]],
        per_token: [["Starting price (US dollars)", f.base], ["Cents for every 1,000 tokens", f.perTok], ["Most one answer can cost (US dollars)", f.price]],
        complexity: [["Light question (cents)", f.light], ["Standard question (cents)", f.standard], ["Deep question (cents)", f.deep]],
        monthly: [["Monthly fee (US dollars)", f.monthly], ["Answers included", f.included]]
      }[mode.v];
      rows.forEach(([t, x]) => fields.append(field(t, x)));
      fields.append(preview); drawPreview();
      Object.values(f).forEach((x) => { x.oninput = drawPreview; });
    };
    drawFields();
    box.append(pick, fields, el("p", "small muted", "Demo money only: nothing real moves in this demo."), field("Where you would be paid", mail));
    const pricing = () => ({
      flat: { plan: "flat", price_usd: parseFloat(f.price.value) },
      per_file: { plan: "per_file", price_usd: parseFloat(f.price.value), base_usd: parseFloat(f.base.value) || 0, per_file_cents: n(f.perFile) },
      per_token: { plan: "per_token", price_usd: parseFloat(f.price.value), base_usd: parseFloat(f.base.value) || 0, per_1k_tokens_cents: n(f.perTok) },
      complexity: { plan: "complexity", light_cents: n(f.light), standard_cents: n(f.standard), deep_cents: n(f.deep) },
      monthly: { plan: "monthly", monthly_usd: parseFloat(f.monthly.value), included_answers: n(f.included) }
    }[mode.v]);
    const go = btn("Publish version " + m.version, "btn go2", async () => {
      go.disabled = true;
      try { await B.api("/api/studio/publish", Object.assign({ id: H.id, payout_email: mail.value }, pricing())); note("Published. The tester is checking it now; this can take a few minutes."); await B.refresh(); await openHelper(H.id); tab = "publish"; drawPanel(); }
      catch (e) { note(e.message); go.disabled = false; }
    }); go.disabled = problems.length > 0; box.append(go);
    box.append(el("h3", "sub", "Your versions"));
    if (!H.versions.length) box.append(el("p", "small muted", "Nothing published yet."));
    H.versions.forEach((v) => {
      const c = el("div", "mem"), [t, cls] = chipFor(v);
      c.append(el("div", null, "Version " + v.version), el("span", "tag " + cls, t));
      c.append(el("div", "small muted", v.answers + " answer" + (v.answers === 1 ? "" : "s") + " given · earned " + B.cents(v.earned_cents) + " · " + v.stars + " fan" + (v.stars === 1 ? "" : "s") + " · " + v.price_text));
      if (v.test_error) c.append(el("div", "small warnline", v.test_error));
      const a = el("div", "acts");
      if (!v.revoked) {
        a.append(btn("Test it again", "btn", async () => { try { await B.api("/api/studio/retest", { key: v.key }); await openHelper(H.id); tab = "publish"; drawPanel(); } catch (e) { note(e.message); } }));
        a.append(btn("Change price", "btn", async () => { try { await B.api("/api/studio/price", Object.assign({ key: v.key, payout_email: mail.value }, pricing())); await B.refresh(); await openHelper(H.id); tab = "publish"; drawPanel(); } catch (e) { note(e.message); } }));
        a.append(btn("Take it off the market", "btn warn", (e) => { if (e.target.dataset.armed) retire(v.key); else { e.target.dataset.armed = "1"; e.target.textContent = "Really?"; setTimeout(() => { delete e.target.dataset.armed; e.target.textContent = "Take it off the market"; }, 3500); } }));
      }
      c.append(a); box.append(c);
    });
    box.append(el("h3", "sub", "Delete this draft"), btn("Delete the draft", "btn warn", async (e) => {
      if (!e.target.dataset.armed) { e.target.dataset.armed = "1"; e.target.textContent = "Really delete?"; setTimeout(() => { delete e.target.dataset.armed; e.target.textContent = "Delete the draft"; }, 3500); return; }
      try { await B.api("/api/studio/delete", { id: H.id }); H = null; await show(); } catch (er) { note(er.message); }
    }));
  }
  async function retire(key) { try { await B.api("/api/studio/retire", { key }); await B.refresh(); await openHelper(H.id); tab = "publish"; drawPanel(); } catch (e) { note(e.message); } }

  /* power users: the steps as text */
  function textPanel(box) {
    box.append(el("p", "small muted", "The steps as written in the file. Changes here replace the picture once they are valid."));
    const t = textarea(H.workflow_text, 18, () => {}); t.maxLength = 30000; t.className = "mono";
    const go = btn("Use this text", "btn go2", async () => {
      try { const r = await B.api("/api/studio/save", { id: H.id, workflow_text: t.value }); H.workflow_text = r.workflow_text; wf = r.workflow; problems = r.problems; sel = null; note(""); drawProblems(); drawGraph(); }
      catch (e) { note(e.message); }
    });
    box.append(t, go);
  }

  /* poll while a version is being tested */
  function watchTests() {
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      if ($("view-studio").hidden || !H) return;
      if (!H.versions.some((v) => v.testing)) return;
      try { const r = await B.api("/api/studio/helper?id=" + encodeURIComponent(H.id)); H.versions = r.versions; if (!r.versions.some((v) => v.testing)) await B.refresh(); if (tab === "publish") drawPanel(); } catch (e) { /* next poll */ }
    }, 3000);
  }

  function mount(bridge) {
    B = bridge;
    $("newform").onsubmit = createHelper;
    ["steps", "about", "try", "publish", "text"].forEach((t) => { $("ptab-" + t).onclick = () => { tab = t; drawPanel(); }; });
    [["addfiles", "files"], ["addweb", "web"], ["addthink", "think"], ["addcheck", "check"], ["addprogram", "program"], ["adddeliver", "deliver"]].forEach(([id, k]) => { $(id).onclick = () => addStep(k); });
    setupGraphView();
    $("tidy").onclick = () => { layout = {}; fitNext = true; changed(["layout"]); drawGraph(); };
    $("showdata").onchange = (e) => { showData = e.target.checked; drawGraph(); };
  }
  window.Studio = { mount, show, redraw: () => {} };
})();
