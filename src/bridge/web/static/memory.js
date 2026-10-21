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
  const note = (t) => { $("memnote").textContent = t || ""; };
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
  /* ---------- the map: shelves inside shelves, and which chats may look at each ---------- */
  const NS = "http://www.w3.org/2000/svg", NW = 200, NH = 46, GX = 44, GY = 12;
  const sv = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (text !== undefined) e.textContent = text; return e; };
  const CHAT_COLORS = ["#CFE5E9", "#F3DACA", "#E0DAF2", "#F3E4BC", "#D2E7DA", "#F3D3CD"];
  let stalls = [];

  function nearestVisible(path) {  // a chat that opened a folded shelf points at the closest shelf you can see
    const vis = new Set(rows.map((r) => r.path));
    for (let p = path; p; p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "") if (vis.has(p)) return p;
    return "";
  }
  let rows = [];
  function drawTree() {
    const svg = $("memmap"); svg.replaceChildren();
    const m = B.state().memory;
    if (!m.total) { svg.setAttribute("viewBox", "0 0 400 80"); svg.style.height = "80px"; svg.append(sv("text", { x: 16, y: 44, "font-size": 14, fill: "#6B5878" }, "Your memory is empty. Add something below, or say yes to a helper's suggestion.")); return; }
    rows = shelves().filter(visible);
    const row = {}; rows.forEach((s, i) => { row[s.path] = i; });
    const maxDepth = Math.max(0, ...rows.map((s) => s.depth)), chatX = 48 + (maxDepth + 1) * (NW + GX) + 20, H = Math.max(rows.length * (NH + GY) + 70, 200);
    const W = chatX + 200;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H); svg.style.minWidth = W + "px"; svg.style.height = H + "px";
    const edges = sv("g"), nodes = sv("g"); svg.append(edges, nodes);
    const y = (p) => 56 + row[p] * (NH + GY);
    const xOf = (d) => 48 + d * (NW + GX);
    // the root: everything
    const root = sv("g", { class: "mnode" + (sel === "" ? " sel" : ""), tabindex: 0, role: "button", "aria-label": "Everything, " + m.total + " files" });
    root.append(sv("rect", { x: 20, y: 6, width: NW, height: 36, rx: 8, fill: "#FFF8E7", stroke: "#1A1320", "stroke-width": sel === "" ? 4 : 2 }), sv("text", { x: 32, y: 29, "font-size": 14, "font-weight": 700 }, "All my memory · " + m.total));
    root.onclick = () => select(""); root.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(""); } };
    nodes.append(root);
    const conn = (x1, y1, x2, y2, col, w, dash) => edges.append(sv("path", { d: "M" + x1 + "," + y1 + " C" + (x1 + 30) + "," + y1 + " " + (x2 - 30) + "," + y2 + " " + x2 + "," + y2, fill: "none", stroke: col, "stroke-width": w, "stroke-dasharray": dash || "" }));
    rows.forEach((s) => {
      const x = xOf(s.depth), yy = y(s.path), isSel = sel === s.path;
      const spine = s.depth === 0 ? 34 : xOf(s.depth - 1) + 14, top = s.depth === 0 ? 42 : (row[s.parent] !== undefined ? y(s.parent) + NH : 42);  // an elbow from the shelf above, like a folder tree
      edges.append(sv("path", { d: "M" + spine + "," + top + " V" + (yy + NH / 2) + " H" + x, fill: "none", stroke: "#A899B5", "stroke-width": 2 }));
      const g = sv("g", { class: "mnode" + (isSel ? " sel" : ""), tabindex: 0, role: "button", "aria-label": s.name + ", " + s.count + " files" + (s.secret ? ", " + s.secret + " secret" : "") });
      g.append(sv("title", {}, s.label || s.name));
      g.append(sv("rect", { x, y: yy, width: NW, height: NH, rx: 8, fill: "#FFFDF5", stroke: "#1A1320", "stroke-width": isSel ? 4 : 2 }));
      g.append(sv("text", { x: x + 12, y: yy + 19, "font-size": 13, "font-weight": 700 }, s.name.length > 18 ? s.name.slice(0, 17) + "…" : s.name));
      g.append(sv("text", { x: x + NW - 12, y: yy + 19, "font-size": 12, "text-anchor": "end", fill: "#3D2E4A" }, s.count + (s.has_children ? (expanded.has(s.path) ? "  ▾" : "  ▸") : "")));
      const bw = NW - 24, total = Math.max(m.total, 1), full = Math.max(8, Math.round(bw * Math.min(1, s.count / total * 3)));  // bar length: how big this shelf is
      const sec = Math.round(full * (s.secret / Math.max(s.count, 1)));
      g.append(sv("rect", { x: x + 12, y: yy + 28, width: full - sec, height: 8, fill: "#5CA97A", stroke: "#1A1320", "stroke-width": 1 }));
      if (sec) g.append(sv("rect", { x: x + 12 + full - sec, y: yy + 28, width: sec, height: 8, fill: "#D96A62", stroke: "#1A1320", "stroke-width": 1 }));
      if (s.label) g.append(sv("text", { x: x + 24 + full, y: yy + 36, "font-size": 10, fill: "#6B5878" }, s.label.length > 16 ? s.label.slice(0, 15) + "…" : s.label));
      g.onclick = () => { if (s.has_children) { expanded.has(s.path) ? (isSel ? expanded.delete(s.path) : 0) : expanded.add(s.path); } select(s.path); };
      g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); g.onclick(); } };
      nodes.append(g);
    });
    // chats on the right, joined to the shelves they may look at
    stalls.forEach((c, i) => {
      const cy = 56 + i * 58, col = CHAT_COLORS[i % CHAT_COLORS.length];
      const g = sv("g", { class: "mchat", tabindex: 0, role: "button", "aria-label": "Chat: " + c.title });
      g.append(sv("rect", { x: chatX, y: cy, width: 170, height: 44, rx: 22, fill: col, stroke: "#1A1320", "stroke-width": 2 }));
      g.append(sv("text", { x: chatX + 85, y: cy + 19, "text-anchor": "middle", "font-size": 12, "font-weight": 700 }, c.title.length > 20 ? c.title.slice(0, 19) + "…" : c.title));
      g.append(sv("text", { x: chatX + 85, y: cy + 34, "text-anchor": "middle", "font-size": 10, fill: "#3D2E4A" }, c.agent.name));
      g.onclick = () => window.ChatUI.open(c.id); g.onkeydown = (e) => { if (e.key === "Enter") window.ChatUI.open(c.id); };
      nodes.append(g);
      (c.paths || []).forEach((p) => { const v = nearestVisible(p); if (v !== "" && row[v] !== undefined) conn(xOf(rows[row[v]].depth) + NW, y(v) + NH / 2, chatX, cy + 22, "#4F9FAF", 3, "7 4"); });
    });
    if (stalls.length) nodes.append(sv("text", { x: chatX, y: 34, "font-size": 12, fill: "#6B5878" }, "Chats that may look"));
    const dl = $("shelfnames"); dl.replaceChildren();
    shelves().forEach((s) => { const o = document.createElement("option"); o.value = s.path; dl.append(o); });
  }
  async function loadChats() { try { stalls = (await B.api("/api/office")).stalls; } catch (e) { stalls = []; } drawTree(); }

  async function select(path) {
    sel = path; offset = 0; if (path) for (let p = path; p.includes("/"); ) { p = p.slice(0, p.lastIndexOf("/")); expanded.add(p); }
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
        if (kind === "move") { const r = await B.api("/api/memory", { action: "move_shelf", from: sel, to: inp.value }); const to = inp.value.trim().toLowerCase().replace(/\s*\/\s*/g, "/"); note("Moved " + r.moved + " file(s)."); sel = to; }
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
    let items;
    try { items = (await B.api("/api/memory?shelf=" + encodeURIComponent(sel) + "&q=" + encodeURIComponent(query) + "&offset=" + offset + "&limit=" + PAGE)).items; }
    catch (e) { note(e.message); return; }
    if (reset && !items.length) box.append(el("p", "empty", query ? "Nothing matches that search." : "Nothing on this shelf yet."));
    items.forEach((r) => box.append(card(r)));
    offset += items.length; more.hidden = items.length < PAGE;
  }

  function card(r) {
    const c = el("div", "mem");
    c.append(el("div", "memtext", r.text));
    const meta = el("div", "small muted");
    meta.append((r.source === "helper" ? "Suggested by " + r.helper + ", saved because you said yes" : "Written by you") + (r.created ? " on " + when(r.created) : "") + ". ");
    meta.append(el("span", "tag " + (r.sensitivity === "low" ? "good" : "wait"), r.sensitivity === "low" ? "Everyday" : "Secret"), " ", r.shelf_name + ".");
    if (r.edited) meta.append(" You corrected it later.");
    c.append(meta);
    c.append(el("div", "small muted", r.used.answers ? "Helped write " + r.used.answers + " answer(s); last in “" + r.used.last_chat + "”." : "Not used in any answer yet."));
    const a = el("div", "acts");
    a.append(btn("Edit", "btn", () => edit(c, r)), btn("Delete", "btn warn", (e) => confirmTwice(e.target, "Really delete?", async () => {
      try { await B.api("/api/memory", { action: "delete", id: r.id }); await B.refresh(); } catch (er) { note(er.message); }
    })));
    c.append(a); return c;
  }

  function edit(c, r) {
    c.replaceChildren();
    const ta = document.createElement("textarea"); ta.value = r.text; ta.rows = 3; ta.maxLength = 2000; ta.setAttribute("aria-label", "Text of this memory");
    const lv = levelSelect(r.sensitivity), sh = document.createElement("input"); sh.type = "text"; sh.value = r.shelf; sh.setAttribute("aria-label", "Shelf"); sh.setAttribute("list", "shelfnames");
    const a = el("div", "acts");
    a.append(btn("Save", "btn go2", async () => {
      try { await B.api("/api/memory", { action: "update", id: r.id, text: ta.value, sensitivity: lv.value, shelf: sh.value }); await B.refresh(); }
      catch (e) { note(e.message); }
    }), btn("Cancel", "btn", () => drawFiles(true)));
    c.append(ta, el("label", "small fieldrow", "Shelf "), sh, lv, a);
  }

  /* ---------- adding and importing ---------- */
  function setupForm() {
    const f = $("memform"), lv = levelSelect("low"); lv.id = "memlevel"; $("memlevelslot").replaceChildren(lv);
    f.onsubmit = async (e) => {
      e.preventDefault();
      try {
        await B.api("/api/memory", { action: "add", type: $("memkind").value, text: $("memtext").value, sensitivity: lv.value, shelf: $("memshelf").value });
        $("memtext").value = ""; note("Saved."); await B.refresh();
      } catch (er) { note(er.message); }
    };
    $("memq").oninput = () => { clearTimeout(queryTimer); queryTimer = setTimeout(() => { query = $("memq").value.trim(); drawFiles(true); }, 300); };
    $("memmore").onclick = () => drawFiles(false);
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
      const notes = splitNotes(await f.text()).slice(0, 50);
      if (!notes.length) { box.append(el("p", "warnline", "There is no text in that file.")); return; }
      box.append(el("p", "small", "Found " + notes.length + " note(s). Untick the ones you do not want."));
      const list = el("ul", "filelist"), boxes = [];
      notes.forEach((t) => { const li = el("li"), c = document.createElement("input"); c.type = "checkbox"; c.checked = true; c.setAttribute("aria-label", "Keep: " + t.slice(0, 60)); boxes.push(c); li.append(c, el("span", null, t)); list.append(li); });
      const lv = levelSelect("low"), shelf = document.createElement("input"); shelf.type = "text"; shelf.setAttribute("list", "shelfnames"); shelf.maxLength = 200; shelf.setAttribute("aria-label", "Shelf for these notes");
      shelf.value = f.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9 -]+/g, " ").trim().slice(0, 30);
      const row = el("div", "composerrow"); row.append(el("label", "small", "Put them on shelf "), shelf, lv);
      const save = btn("Save the ticked notes", "btn go2", async () => {
        const keep = notes.filter((_, i) => boxes[i].checked); if (!keep.length) { note("Tick at least one note."); return; }
        save.disabled = true;
        try { await B.api("/api/memory", { action: "add_many", items: keep, sensitivity: lv.value, type: "note", shelf: shelf.value }); box.replaceChildren(); $("memfile").value = ""; note("Saved " + keep.length + " note(s)."); await B.refresh(); }
        catch (e) { note(e.message); save.disabled = false; }
      });
      box.append(list, row, save);
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
  function show() { redraw(); }
  function mount(bridge) {
    B = bridge; setupForm(); setupImport(); redraw();
    $("mapexpand").onclick = () => { shelves().forEach((s) => { if (s.has_children) expanded.add(s.path); }); drawTree(); };
    $("mapfold").onclick = () => { expanded.clear(); drawTree(); };
  }
  window.MemoryUI = { mount, redraw, show, proposals, pretty };
})();
