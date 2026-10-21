/* My memory: a library with shelves. The tree on the left shows every shelf with how many files lie under it, the list on
   the right pages through the files of one shelf. Only titles and counts are loaded for the tree, so a very large memory
   stays fast. Plain language only; every string from the server is inserted with textContent. */
(function () {
  "use strict";
  let B = null, sel = "", expanded = new Set(), offset = 0, query = "", queryTimer = null;
  const PAGE = 30;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const btn = (text, cls, fn) => { const b = el("button", cls || "btn", text); b.type = "button"; if (fn) b.onclick = fn; return b; };
  const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");
  const pretty = (p) => (p ? p.split("/").map((x) => x.replace(/^./, (c) => c.toUpperCase())).join(" › ") : "Everything");
  const note = (t) => { $("memnote").textContent = ""; if (t) B.toast(t, !/^(Saved|Moved)/.test(t)); };
  const shelves = () => (B.state().memory ? B.state().memory.shelves : []);

  function confirmTwice(b, label, fn) {
    if (b.dataset.armed) { fn(); return; }
    const old = b.textContent; b.dataset.armed = "1"; b.textContent = label;
    setTimeout(() => { delete b.dataset.armed; b.textContent = old; }, 4000);
  }

  function levelSelect(v) {
    const s = document.createElement("select"); s.setAttribute("aria-label", "Everyday or secret");
    [["low", "Everyday: helpers can be given this"], ["high", "Secret: never leaves this page"]].forEach(([k, t]) => { const o = document.createElement("option"); o.value = k; o.textContent = t; s.append(o); });
    s.value = v === "low" ? "low" : "high"; return s;
  }

  /* ---------- suggestions from helpers (shown here and on the market floor) ---------- */
  function proposals(box, after) {
    box.replaceChildren();
    const list = B.state().proposals;
    list.forEach((p) => {
      const n = el("div", "note"); n.append(el("div", null, "“" + p.text + "”"), el("div", "muted small", "A helper suggests you remember this. It is not saved unless you say yes."));
      const a = el("div", "acts");
      const go = async (action) => { try { await B.api("/api/proposal", { id: p.id, action }); await B.refresh(); if (after) after(); } catch (e) { note(e.message); } };
      a.append(btn("Remember it", "btn", () => go("accept")), btn("No thanks", "btn", () => go("reject")));
      n.append(a); box.append(n);
    });
    return list.length;
  }

  /* ---------- the tree ---------- */
  function visible(s) {
    for (let p = s.parent; p; p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "") if (!expanded.has(p)) return false;
    return true;
  }
  /* ---------- the map: shelves inside shelves, files on the open shelf, and the chats that may look at each ---------- */
  const NS = "http://www.w3.org/2000/svg", NW = 200, NH = 46, GX = 44, GY = 12;
  const sv = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (text !== undefined) e.textContent = text; return e; };
  const CHAT_COLORS = ["#CFE5E9", "#F3DACA", "#E0DAF2", "#F3E4BC", "#D2E7DA", "#F3D3CD"];
  const MAX_LEAVES = 14;
  let stalls = [], leaf = [], selFile = null, view = { k: 1, x: 10, y: 10 }, fitNext = true, size = { w: 0, h: 0 }, visiblePaths = new Set(), panning = false;
  const snip = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

  function nearestVisible(path) {  // a chat that opened a folded shelf points at the closest shelf you can see
    for (let p = path; p; p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "") if (visiblePaths.has(p)) return p;
    return "";
  }
  function applyView() { const vp = $("vp"); if (vp) vp.setAttribute("transform", "translate(" + view.x + " " + view.y + ") scale(" + view.k + ")"); }
  function fit() {
    const r = $("memmap").getBoundingClientRect(); if (!r.width || !size.w) return;
    const k = Math.min((r.width - 20) / size.w, (r.height - 20) / size.h, 1.2);
    view = { k, x: Math.max(10, (r.width - size.w * k) / 2), y: 10 }; applyView();
  }
  function zoomAt(f, px, py) {
    const k2 = Math.min(2.5, Math.max(0.25, view.k * f)), s = k2 / view.k;
    view = { k: k2, x: px - (px - view.x) * s, y: py - (py - view.y) * s }; applyView();
  }
  function setupView() {
    const svg = $("memmap");
    svg.addEventListener("wheel", (e) => { e.preventDefault(); const r = svg.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); }, { passive: false });
    svg.addEventListener("pointerdown", (e) => {
      if (e.target.closest && e.target.closest(".mnode,.mchat,.mfile")) return;
      panning = true; const sx = e.clientX, sy = e.clientY, ox = view.x, oy = view.y; svg.style.cursor = "grabbing";
      const move = (ev) => { view.x = ox + ev.clientX - sx; view.y = oy + ev.clientY - sy; applyView(); };
      const up = () => { panning = false; svg.style.cursor = ""; window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
    });
    const mid = () => { const r = svg.getBoundingClientRect(); return [r.width / 2, r.height / 2]; };
    $("mapzoomin").onclick = () => zoomAt(1.25, ...mid()); $("mapzoomout").onclick = () => zoomAt(1 / 1.25, ...mid()); $("mapfit").onclick = fit;
    window.addEventListener("resize", () => { if (!$("view-memory").hidden) fit(); });
  }

  /* A soft mind map: the memory sits in the middle, shelves grow outwards as bubbles (bigger bubble = more files),
     branches are smooth curves, and each main branch has its own colour. */
  const BRANCH = [["#F6D7A7", "#D9A441"], ["#CDE8D6", "#5CA97A"], ["#CFE5F0", "#4F9FAF"], ["#E3DCF5", "#9482D3"], ["#F7D4CF", "#D96A62"], ["#F5E6B8", "#C9A227"]];
  const bubbleR = (count) => Math.min(62, 30 + 6 * Math.sqrt(Math.max(count, 1)));

  function drawTree() {
    const svg = $("memmap"); svg.replaceChildren();
    const m = B.state().memory;
    if (!m.total) { svg.append(sv("text", { x: 16, y: 44, "font-size": 14, fill: "#6B5878" }, "Your memory is empty. Add something below, or say yes to a helper's suggestion.")); return; }
    const defs = sv("defs");
    defs.append(sv("filter", { id: "soft", x: "-30%", y: "-30%", width: "160%", height: "160%" }));
    defs.lastChild.append(sv("feDropShadow", { dx: 0, dy: 3, stdDeviation: 4, "flood-color": "#3D2E4A", "flood-opacity": 0.22 }));
    svg.append(defs);
    const vp = sv("g", { id: "vp" }); svg.append(vp);
    const inner = sv("g"); vp.append(inner);
    const edges = sv("g"), nodes = sv("g"); inner.append(edges, nodes);

    // 1. the visible tree: shelves, plus the files of the open shelf
    const vis = shelves().filter(visible), byParent = {};
    vis.forEach((s) => { (byParent[s.parent] = byParent[s.parent] || []).push(s); });
    const mk = (s, depth, branch) => {
      const n = { kind: "shelf", s, depth, branch, kids: [] };
      (byParent[s.path] || []).forEach((c) => n.kids.push(mk(c, depth + 1, branch)));
      if (s.path === sel) {
        leaf.slice(0, MAX_LEAVES).forEach((f) => n.kids.push({ kind: "file", f, depth: depth + 1, branch, kids: [], w: 0.6 }));
        if (leaf.length > MAX_LEAVES) n.kids.push({ kind: "more", n: leaf.length - MAX_LEAVES, depth: depth + 1, branch, kids: [], w: 0.6 });
      }
      return n;
    };
    const top = (byParent[""] || []).map((s, i) => mk(s, 1, i % BRANCH.length));
    const weight = (n) => (n.kids.length ? n.kids.reduce((a, k) => a + weight(k), 0) : n.w || 1);
    const perDepth = {}; const count = (n) => { perDepth[n.depth] = (perDepth[n.depth] || 0) + 1; n.kids.forEach(count); }; top.forEach(count);
    const R = { 0: 0 }; Object.keys(perDepth).map(Number).sort((a, b) => a - b).forEach((d) => { R[d] = Math.max((R[d - 1] || 0) + (d === 1 ? 210 : 170), perDepth[d] * 96 / (2 * Math.PI)); });
    const place = (list, a0, a1) => {
      const total = list.reduce((a, n) => a + weight(n), 0) || 1; let a = a0;
      list.forEach((n) => { const span = (a1 - a0) * weight(n) / total, mid = a + span / 2; n.x = Math.cos(mid) * R[n.depth]; n.y = Math.sin(mid) * R[n.depth]; n.ang = mid; place(n.kids, a, a + span); a += span; });
    };
    place(top, -Math.PI / 2, Math.PI * 1.5);
    const all = []; const flat = (n, parent) => { n.parent = parent; all.push(n); n.kids.forEach((k) => flat(k, n)); }; const rootNode = { kind: "root", x: 0, y: 0, kids: top, depth: 0 }; flat(rootNode, null);
    visiblePaths = new Set(all.filter((n) => n.kind === "shelf").map((n) => n.s.path));
    const posOf = {}; all.forEach((n) => { if (n.kind === "shelf") posOf[n.s.path] = n; });

    // 2. the edges: smooth curves, thicker where there is more
    all.forEach((n) => {
      if (!n.parent) return;
      const a = n.parent, col = BRANCH[n.branch % BRANCH.length][1], w = n.kind === "shelf" ? Math.min(9, 2.5 + Math.sqrt(n.s.count)) : 2;
      const mx = (a.x + n.x) / 2, my = (a.y + n.y) / 2, k = 0.18;
      edges.append(sv("path", { d: "M" + a.x + "," + a.y + " Q" + (mx - (n.y - a.y) * k) + "," + (my + (n.x - a.x) * k) + " " + n.x + "," + n.y, fill: "none", stroke: col, "stroke-width": w, "stroke-linecap": "round", opacity: 0.55 }));
    });

    // 3. the bubbles
    const label = (g, text, x, y, size, weight, anchor) => {
      const t = sv("text", { x, y, "text-anchor": anchor || "middle", "font-size": size, "font-weight": weight || 600, class: "mlabel" }, text); g.append(t); return t;
    };
    const rootG = sv("g", { class: "mnode bub" + (sel === "" ? " sel" : ""), tabindex: 0, role: "button", "aria-label": "Everything, " + m.total + " files" });
    const ri = sv("g", { class: "bubi" });
    ri.append(sv("circle", { r: 62, fill: "url(#g-root)", stroke: "#1A1320", "stroke-width": sel === "" ? 4 : 2.5, filter: "url(#soft)" }));
    label(ri, "My memory", 0, -2, 14, 700); label(ri, m.total + " files", 0, 17, 12, 500);
    rootG.append(ri); rootG.setAttribute("transform", "translate(0 0)");
    rootG.onclick = () => select(""); rootG.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(""); } };
    BRANCH.forEach(([a, b], i) => { const gr = sv("radialGradient", { id: "g-" + i, cx: "35%", cy: "30%", r: "80%" }); gr.append(sv("stop", { offset: "0%", "stop-color": "#FFFFFF" }), sv("stop", { offset: "100%", "stop-color": a })); defs.append(gr); });
    { const gr = sv("radialGradient", { id: "g-root", cx: "35%", cy: "30%", r: "80%" }); gr.append(sv("stop", { offset: "0%", "stop-color": "#FFFDF5" }), sv("stop", { offset: "100%", "stop-color": "#F3E4BC" })); defs.append(gr); }
    nodes.append(rootG);
    all.forEach((n) => {
      if (n.kind === "root") return;
      const col = BRANCH[n.branch % BRANCH.length];
      if (n.kind === "more") { const t = sv("text", { x: n.x, y: n.y + 4, "text-anchor": "middle", "font-size": 12, fill: "#6B5878" }, "…and " + n.n + " more (see the list)"); nodes.append(t); return; }
      if (n.kind === "file") {
        const f = n.f, on = selFile === f.id, g = sv("g", { class: "mfile bub pop", tabindex: 0, role: "button", "aria-label": "File: " + snip(f.text, 60) });
        g.setAttribute("transform", "translate(" + n.x + " " + n.y + ")"); g.append(sv("title", {}, f.text));
        const gi = sv("g", { class: "bubi" }), txt = (f.sensitivity === "low" ? "" : "🔒 ") + (f.long ? "📄 " + snip(f.title, 22) : snip(f.text, 26)), w = Math.max(70, txt.length * 6.2 + 20);
        gi.append(sv("rect", { x: -w / 2, y: -15, width: w, height: 30, rx: 15, fill: f.sensitivity === "low" ? "#E6F3EA" : "#F9DDD9", stroke: on ? "#1A1320" : col[1], "stroke-width": on ? 3.5 : 2, filter: "url(#soft)" }));
        label(gi, txt, 0, 4, 11, 500); g.append(gi);
        g.onclick = () => { selFile = f.id; drawTree(); drawFiles(true); }; g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); g.onclick(); } };
        nodes.append(g); return;
      }
      const s = n.s, r = bubbleR(s.count), isSel = sel === s.path;
      const g = sv("g", { class: "mnode bub" + (isSel ? " sel" : ""), tabindex: 0, role: "button", "aria-label": s.name + ", " + s.count + " files" + (s.secret ? ", " + s.secret + " secret" : "") });
      g.setAttribute("transform", "translate(" + n.x + " " + n.y + ")"); g.append(sv("title", {}, s.label || s.name));
      const gi = sv("g", { class: "bubi" });
      gi.append(sv("circle", { r, fill: "url(#g-" + (n.branch % BRANCH.length) + ")", stroke: isSel ? "#1A1320" : col[1], "stroke-width": isSel ? 4 : 2.5, filter: "url(#soft)" }));
      if (s.secret) {  // the red ring shows how much of this shelf is secret
        const c = 2 * Math.PI * (r + 5), part = c * (s.secret / Math.max(s.count, 1));
        gi.append(sv("circle", { r: r + 5, fill: "none", stroke: "#D96A62", "stroke-width": 4, "stroke-linecap": "round", "stroke-dasharray": part + " " + c, transform: "rotate(-90)" }));
      }
      label(gi, String(s.count), 0, 6, 17, 700);
      if (s.has_children) label(gi, expanded.has(s.path) ? "▾" : "▸", 0, -r * 0.45, 11, 500);
      const nm = label(gi, snip(s.name, 16), 0, r + 22, 15, 700);
      g.append(gi);
      if (s.label) { const t = label(gi, snip(s.label, 22), 0, r + 35, 10.5, 400); t.setAttribute("fill", "#6B5878"); }
      g.onclick = () => { if (s.has_children) { expanded.has(s.path) ? (isSel ? expanded.delete(s.path) : 0) : expanded.add(s.path); } select(s.path); };
      g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); g.onclick(); } };
      nodes.append(g);
    });

    // 4. the chats, on the right, joined to the shelves they may look at
    let minX = 0, maxX = 0, minY = 0, maxY = 0;
    all.forEach((n) => { const pad = n.kind === "shelf" ? bubbleR(n.s.count) + 50 : n.kind === "file" ? 130 : 60; minX = Math.min(minX, n.x - pad); maxX = Math.max(maxX, n.x + pad); minY = Math.min(minY, n.y - pad); maxY = Math.max(maxY, n.y + pad); });
    const chatX = maxX + 70;
    stalls.forEach((c, i) => {
      const cy = minY + 60 + i * 76, col = CHAT_COLORS[i % CHAT_COLORS.length];
      const g = sv("g", { class: "mchat bub", tabindex: 0, role: "button", "aria-label": "Chat: " + c.title }); g.setAttribute("transform", "translate(" + chatX + " " + cy + ")");
      const gi = sv("g", { class: "bubi" });
      gi.append(sv("rect", { x: 0, y: -26, width: 176, height: 52, rx: 26, fill: col, stroke: "#4F9FAF", "stroke-width": 2.5, filter: "url(#soft)" }));
      label(gi, snip(c.title, 20), 88, -2, 12.5, 700); label(gi, c.agent.name, 88, 14, 10.5, 400); g.append(gi);
      g.onclick = () => window.ChatUI.open(c.id); g.onkeydown = (e) => { if (e.key === "Enter") window.ChatUI.open(c.id); };
      nodes.append(g);
      (c.paths || []).forEach((p) => {
        const v = nearestVisible(p), n = v === "" ? null : posOf[v]; if (!n) return;
        const r = bubbleR(n.s.count), x1 = n.x + r, y1 = n.y, x2 = chatX, y2 = cy, dx = Math.max(60, (x2 - x1) / 2);
        edges.append(sv("path", { d: "M" + x1 + "," + y1 + " C" + (x1 + dx) + "," + y1 + " " + (x2 - dx) + "," + y2 + " " + x2 + "," + y2, fill: "none", stroke: "#4F9FAF", "stroke-width": 3, "stroke-dasharray": "2 9", "stroke-linecap": "round" }));
      });
    });
    if (stalls.length) { const t = sv("text", { x: chatX, y: minY + 22, "font-size": 12, fill: "#6B5878" }, "Chats that may look here"); nodes.append(t); maxX = chatX + 190; }
    const dl = $("shelfnames"); dl.replaceChildren();
    shelves().forEach((s) => { const o = document.createElement("option"); o.value = s.path; dl.append(o); });

    // 5. frame it: shift so the top-left is at the origin, remember the size for "Fit"
    inner.setAttribute("transform", "translate(" + (-minX + 20) + " " + (-minY + 20) + ")");
    size = { w: maxX - minX + 40, h: Math.max(maxY - minY, stalls.length * 76 + 80) + 40 };
    if (fitNext) { fitNext = false; fit(); } else applyView();
  }
  async function loadChats() { try { stalls = (await B.api("/api/office")).stalls; } catch (e) { stalls = []; } drawTree(); }

  async function select(path) {
    sel = path; selFile = null; offset = 0; leaf = [];
    if (path) for (let p = path; p.includes("/"); ) { p = p.slice(0, p.lastIndexOf("/")); expanded.add(p); }
    if (path) { try { leaf = (await B.api("/api/memory?shelf=" + encodeURIComponent(path) + "&limit=100")).items.filter((f) => f.shelf === path); } catch (e) { leaf = []; } }
    drawTree(); drawShelfActions(); await drawFiles(true);
  }

  function drawShelfActions() {
    const box = $("shelfactions"); box.replaceChildren();
    $("shelftitle").textContent = sel ? "Files on “" + pretty(sel) + "” and below" : "All files";
    if (!sel) return;
    const s = shelves().find((x) => x.path === sel); if (!s) return;
    box.append(btn("Rename or move this shelf", "btn", () => shelfForm("move")), btn(s.label ? "Change the note about it" : "Add a note about this shelf", "btn", () => shelfForm("note")));
    const f = el("div", "shelfform"); f.id = "shelfform"; box.append(f);
  }
  function shelfForm(kind) {
    const f = $("shelfform"); f.replaceChildren();
    const s = shelves().find((x) => x.path === sel), inp = document.createElement("input"); inp.type = "text"; inp.maxLength = 200;
    inp.value = kind === "move" ? sel : (s ? s.label : ""); inp.setAttribute("aria-label", kind === "move" ? "New shelf path" : "A short note about this shelf");
    const go = btn("Save", "btn go2", async () => {
      try {
        if (kind === "move") { const r = await B.api("/api/memory", { action: "move_shelf", from: sel, to: inp.value }); const to = inp.value.trim().toLowerCase().replace(/\s*\/\s*/g, "/"); note("Moved " + window.plural(r.moved, "note") + "."); sel = to; }
        else { await B.api("/api/memory", { action: "shelf_note", shelf: sel, text: inp.value }); note("Saved."); }
        await B.refresh(); await select(sel);
      } catch (e) { note(e.message); }
    });
    f.append(el("label", "small", kind === "move" ? "New place, like work/clients: " : "Note: "), inp, go);
    inp.focus();
  }

  /* ---------- the files on a shelf ---------- */
  async function drawFiles(reset) {
    const box = $("memlist"), more = $("memmore");
    if (reset) { box.replaceChildren(); offset = 0; }
    if (reset && selFile) {  // a file picked on the map is shown in full at the top
      try { const one = (await B.api("/api/memory?ids=" + encodeURIComponent(selFile))).items[0]; if (one) { const c = card(one); c.classList.add("picked"); box.append(c); } } catch (e) { /* the list below still works */ }
    }
    let items;
    try { items = (await B.api("/api/memory?shelf=" + encodeURIComponent(sel) + "&q=" + encodeURIComponent(query) + "&offset=" + offset + "&limit=" + PAGE)).items; }
    catch (e) { note(e.message); return; }
    if (reset && !items.length) box.append(el("p", "empty", query ? "Nothing matches that search." : "Nothing on this shelf yet."));
    items.filter((r) => r.id !== selFile).forEach((r) => box.append(card(r)));
    offset += items.length; more.hidden = items.length < PAGE;
  }

  function card(r) {
    const c = el("div", "mem" + (r.long ? " longnote" : ""));
    if (r.long) {
      c.append(el("div", "notetitle", "📄 " + r.title));
      const body = el("div", "memtext", r.text.length > 420 ? r.text.slice(0, 420).trimEnd() + "…" : r.text);
      c.append(body);
      if (r.text.length > 420) {
        const more = btn("Read the whole note (" + r.chars.toLocaleString() + " characters)", "linkbtn", () => {
          const open = more.dataset.open === "1"; more.dataset.open = open ? "0" : "1";
          body.textContent = open ? r.text.slice(0, 420).trimEnd() + "…" : r.text; body.classList.toggle("fulltext", !open);
          more.textContent = open ? "Read the whole note (" + r.chars.toLocaleString() + " characters)" : "Show less";
        });
        c.append(more);
      }
    } else c.append(el("div", "memtext", r.text));
    const meta = el("div", "small muted");
    meta.append((r.source === "helper" ? "Suggested by " + r.helper + ", saved because you said yes" : "Written by you") + (r.created ? " on " + when(r.created) : "") + ". ");
    meta.append(el("span", "tag " + (r.sensitivity === "low" ? "good" : "wait"), r.sensitivity === "low" ? "Everyday" : "Secret"), " ", r.shelf_name + ".");
    if (r.long) meta.append(" Kept whole, stored as " + r.parts + " passages so a helper reads only the part it needs.");
    if (r.edited) meta.append(" You corrected it later.");
    c.append(meta);
    c.append(el("div", "small muted", r.used.answers ? "Helped write " + window.plural(r.used.answers, "answer") + "; last in “" + r.used.last_chat + "”." : "Not used in any answer yet."));
    const a = el("div", "acts");
    a.append(btn("Edit", "btn", () => edit(c, r)), btn("Delete", "btn warn", (e) => confirmTwice(e.target, "Really delete?", async () => {
      try { await B.api("/api/memory", { action: "delete", id: r.id }); await B.refresh(); } catch (er) { note(er.message); }
    })));
    c.append(a); return c;
  }

  function edit(c, r) {
    c.replaceChildren();
    const ta = document.createElement("textarea"); ta.value = r.text; ta.rows = r.long ? 14 : 4; ta.maxLength = 80000; ta.setAttribute("aria-label", "Text of this memory");
    const ti = document.createElement("input"); ti.type = "text"; ti.maxLength = 120; ti.value = r.title || ""; ti.setAttribute("aria-label", "Title of this long note");
    const lv = levelSelect(r.sensitivity), sh = document.createElement("input"); sh.type = "text"; sh.value = r.shelf; sh.setAttribute("aria-label", "Shelf"); sh.setAttribute("list", "shelfnames");
    const a = el("div", "acts");
    a.append(btn("Save", "btn go2", async () => {
      try { await B.api("/api/memory", Object.assign({ action: "update", id: r.id, text: ta.value, sensitivity: lv.value, shelf: sh.value }, r.long ? { title: ti.value } : {})); await B.refresh(); }
      catch (e) { note(e.message); }
    }), btn("Cancel", "btn", () => drawFiles(true)));
    c.append(ta); if (r.long) c.append(el("label", "small fieldrow", "Title "), ti);
    c.append(el("label", "small fieldrow", "Shelf "), sh, lv, a);
  }

  /* ---------- adding and importing ---------- */
  function setupForm() {
    const f = $("memform"), lv = levelSelect("low"); lv.id = "memlevel"; $("memlevelslot").replaceChildren(lv);
    f.onsubmit = async (e) => {
      e.preventDefault();
      try {
        const r = await B.api("/api/memory", { action: "add", type: $("memkind").value, text: $("memtext").value, sensitivity: lv.value, shelf: $("memshelf").value, title: $("memtitle").value });
        $("memtext").value = ""; $("memtitle").value = ""; countChars(); note(r.id.startsWith("doc") ? "Saved as one long note." : "Saved."); await B.refresh();
      } catch (er) { note(er.message); }
    };
    $("memtext").oninput = countChars; countChars();
    $("memq").oninput = () => { clearTimeout(queryTimer); queryTimer = setTimeout(() => { query = $("memq").value.trim(); drawFiles(true); }, 300); };
    $("memmore").onclick = () => drawFiles(false);
  }

  function countChars() {
    const n = $("memtext").value.length, long = n > 1500;
    $("memcount").textContent = n ? n.toLocaleString() + " of 80,000 characters" + (long ? ". This is a long note: it is kept whole and cut into passages for helpers." : "") : "";
    $("memtitlerow").hidden = !long;
  }

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
      const raw = (await f.text()).replace(/\r\n/g, "\n").trim();
      if (!raw) { box.append(el("p", "warnline", "There is no text in that file.")); return; }
      const lv = levelSelect("low"), shelf = document.createElement("input"); shelf.type = "text"; shelf.setAttribute("list", "shelfnames"); shelf.maxLength = 200; shelf.setAttribute("aria-label", "Shelf for these notes");
      const base = f.name.replace(/\.[^.]+$/, ""); shelf.value = base.toLowerCase().replace(/[^a-z0-9 -]+/g, " ").trim().slice(0, 30);
      const canWhole = raw.length <= 80000, mode = { v: canWhole ? "whole" : "split" };
      const pick = el("div", "modepick");
      [["whole", "Keep it as one long note (" + raw.length.toLocaleString() + " characters)"], ["split", "Split it into short notes"]].forEach(([v, t]) => {
        const l = el("label", "small"), r = document.createElement("input"); r.type = "radio"; r.name = "impmode"; r.value = v; r.checked = mode.v === v; r.disabled = v === "whole" && !canWhole;
        r.onchange = () => { mode.v = v; drawList(); }; l.append(r, " " + t); pick.append(l);
      });
      const listBox = el("div"), notes = splitNotes(raw).slice(0, 50), boxes = [];
      const drawList = () => {
        listBox.replaceChildren(); boxes.length = 0;
        if (mode.v === "whole") { listBox.append(el("p", "small muted", "It will be saved whole and cut into passages behind the scenes.")); return; }
        listBox.append(el("p", "small", "Found " + window.plural(notes.length, "note") + ". Untick the ones you do not want."));
        const list = el("ul", "filelist");
        notes.forEach((t) => { const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = true; c.setAttribute("aria-label", "Keep: " + t.slice(0, 60)); boxes.push(c); li.append(c, el("span", null, t)); list.append(li); });
        listBox.append(list);
      };
      drawList();
      const row = el("div", "composerrow"); row.append(el("label", "small", "Put it on shelf "), shelf, lv);
      const save = btn("Save", "btn go2", async () => {
        const items = mode.v === "whole" ? [{ title: base, text: raw }] : notes.filter((_, i) => boxes[i].checked);
        if (!items.length) { note("Tick at least one note."); return; }
        save.disabled = true;
        try { await B.api("/api/memory", { action: "add_many", items, sensitivity: lv.value, type: "note", shelf: shelf.value }); box.replaceChildren(); $("memfile").value = ""; note("Saved."); await B.refresh(); }
        catch (e) { note(e.message); save.disabled = false; }
      });
      box.append(pick, listBox, row, save);
    };
  }

  function redraw() {
    const m = B.state().memory;
    if (sel && !shelves().some((s) => s.path === sel)) sel = "";
    proposals($("suggest"));
    drawTree(); drawShelfActions(); loadChats();
    if (!$("view-memory").hidden) drawFiles(true);
    const np = $("notespanel"); if (np) { const n = proposals($("notes")); np.hidden = !n; }
  }
  function show() { fitNext = true; redraw(); }
  function mount(bridge) {
    B = bridge; setupForm(); setupImport(); redraw();
    setupView();
    $("mapexpand").onclick = () => { shelves().forEach((s) => { if (s.has_children) expanded.add(s.path); }); fitNext = true; drawTree(); };
    $("mapfold").onclick = () => { expanded.clear(); fitNext = true; drawTree(); };
  }
  window.MemoryUI = { mount, redraw, show, proposals, pretty };
})();
