/* A soft mind map of the memory: the memory sits in the middle, shelves grow outwards as bubbles (a bigger bubble holds
   more notes), branches are smooth curves and each main branch has its own colour. The files of the open shelf appear as
   pills around it, and the chats that may look at a shelf are joined to it by a dotted line. */
import { sv } from "../lib/dom.js";
import { snip } from "../lib/format.js";
import { PanZoom } from "../lib/panzoom.js";

const BRANCH = [["#F6D7A7", "#D9A441"], ["#CDE8D6", "#5CA97A"], ["#CFE5F0", "#4F9FAF"], ["#E3DCF5", "#9482D3"], ["#F7D4CF", "#D96A62"], ["#F5E6B8", "#C9A227"]];
const CHAT_COLORS = ["#CFE5E9", "#F3DACA", "#E0DAF2", "#F3E4BC", "#D2E7DA", "#F3D3CD"];
const MAX_LEAVES = 14;
const bubbleR = (count) => Math.min(62, 30 + 6 * Math.sqrt(Math.max(count, 1)));
const parentOf = (p) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");

export class MemoryMap {
  /**
   * svg: the <svg>.
   * on: { shelf(path), file(note), chat(id) } — what to do when something on the map is clicked.
   */
  constructor(svg, on) {
    this.svg = svg;
    this.on = on;
    this.pz = new PanZoom(svg, { skip: ".mnode,.mchat,.mfile" });
    this.expanded = new Set();
    this.data = { memory: null, shelves: [], sel: "", selFile: null, leaf: [], stalls: [] };
    this.fitNext = true;
    this.visiblePaths = new Set();
  }

  set(data) { this.data = { ...this.data, ...data }; }

  expandAll() { this.data.shelves.forEach((s) => { if (s.has_children) this.expanded.add(s.path); }); this.fitNext = true; this.draw(); }
  foldAll() { this.expanded.clear(); this.fitNext = true; this.draw(); }

  /** A click on a shelf: open it (or fold it if it was already the selected one), then ask the view to select it. */
  clickShelf(s) {
    if (s.has_children) {
      if (!this.expanded.has(s.path)) this.expanded.add(s.path);
      else if (this.data.sel === s.path) this.expanded.delete(s.path);
    }
    this.on.shelf(s.path);
  }

  /** Open every shelf above `path`, so a selected shelf is always visible on the map. */
  reveal(path) {
    for (let p = parentOf(path || ""); p; p = parentOf(p)) this.expanded.add(p);
  }

  #visible(s) {
    for (let p = s.parent; p; p = parentOf(p)) if (!this.expanded.has(p)) return false;
    return true;
  }

  #nearestVisible(path) {  // a chat that opened a folded shelf points at the closest shelf you can see
    for (let p = path; p; p = parentOf(p)) if (this.visiblePaths.has(p)) return p;
    return "";
  }

  draw() {
    const { memory, shelves, sel, selFile, leaf, stalls } = this.data, svg = this.svg;
    svg.replaceChildren();
    if (!memory || !memory.total) { svg.append(sv("text", { x: 16, y: 44, "font-size": 14, fill: "#6B5878" }, "Your memory is empty. Add something below, or say yes to a helper's suggestion.")); return; }

    const defs = sv("defs"), shadow = sv("filter", { id: "soft", x: "-30%", y: "-30%", width: "160%", height: "160%" });
    shadow.append(sv("feDropShadow", { dx: 0, dy: 3, stdDeviation: 4, "flood-color": "#3D2E4A", "flood-opacity": 0.22 }));
    defs.append(shadow);
    BRANCH.forEach(([a], i) => defs.append(this.#gradient("g-" + i, "#FFFFFF", a)));
    defs.append(this.#gradient("g-root", "#FFFDF5", "#F3E4BC"));
    svg.append(defs);
    const vp = sv("g"), inner = sv("g"), edges = sv("g"), nodes = sv("g");
    vp.append(inner); inner.append(edges, nodes); svg.append(vp);

    const all = this.#layout(shelves, sel, leaf);
    this.visiblePaths = new Set(all.filter((n) => n.kind === "shelf").map((n) => n.s.path));
    const posOf = {};
    all.forEach((n) => { if (n.kind === "shelf") posOf[n.s.path] = n; });

    all.forEach((n) => { if (n.parent) edges.append(this.#edge(n)); });
    nodes.append(this.#rootNode(memory, sel));
    all.forEach((n) => { const g = this.#node(n, sel, selFile); if (g) nodes.append(g); });

    // the chats, on the right, joined to the shelves they may look at
    let minX = 0, maxX = 0, minY = 0, maxY = 0;
    all.forEach((n) => {
      const pad = n.kind === "shelf" ? bubbleR(n.s.count) + 50 : n.kind === "file" ? 130 : 60;
      minX = Math.min(minX, n.x - pad); maxX = Math.max(maxX, n.x + pad); minY = Math.min(minY, n.y - pad); maxY = Math.max(maxY, n.y + pad);
    });
    const chatX = maxX + 70;
    stalls.forEach((c, i) => {
      const cy = minY + 60 + i * 76;
      nodes.append(this.#chatPill(c, chatX, cy, CHAT_COLORS[i % CHAT_COLORS.length]));
      (c.paths || []).forEach((p) => {
        const v = this.#nearestVisible(p), n = v === "" ? null : posOf[v];
        if (n) edges.append(this.#chatEdge(n, chatX, cy));
      });
    });
    if (stalls.length) { nodes.append(sv("text", { x: chatX, y: minY + 22, "font-size": 12, fill: "#6B5878" }, "Chats that may look here")); maxX = chatX + 190; }

    // frame it: shift so the top-left is at the origin, and remember the size for "Fit"
    inner.setAttribute("transform", `translate(${-minX + 20} ${-minY + 20})`);
    this.pz.setViewport(vp, { w: maxX - minX + 40, h: Math.max(maxY - minY, stalls.length * 76 + 80) + 40 });
    if (this.fitNext) { this.fitNext = false; this.pz.fitSoon(); }
  }

  #gradient(id, from, to) {
    const g = sv("radialGradient", { id, cx: "35%", cy: "30%", r: "80%" });
    g.append(sv("stop", { offset: "0%", "stop-color": from }), sv("stop", { offset: "100%", "stop-color": to }));
    return g;
  }

  /** Place every visible shelf (and the files of the open one) on rings around the middle. */
  #layout(shelves, sel, leaf) {
    const byParent = {};
    shelves.filter((s) => this.#visible(s)).forEach((s) => { (byParent[s.parent] = byParent[s.parent] || []).push(s); });
    const make = (s, depth, branch) => {
      const n = { kind: "shelf", s, depth, branch, kids: [] };
      (byParent[s.path] || []).forEach((c) => n.kids.push(make(c, depth + 1, branch)));
      if (s.path === sel) {
        leaf.slice(0, MAX_LEAVES).forEach((f) => n.kids.push({ kind: "file", f, depth: depth + 1, branch, kids: [], w: 0.6 }));
        if (leaf.length > MAX_LEAVES) n.kids.push({ kind: "more", n: leaf.length - MAX_LEAVES, depth: depth + 1, branch, kids: [], w: 0.6 });
      }
      return n;
    };
    const top = (byParent[""] || []).map((s, i) => make(s, 1, i % BRANCH.length));
    const weight = (n) => (n.kids.length ? n.kids.reduce((a, k) => a + weight(k), 0) : n.w || 1);
    const perDepth = {};
    const count = (n) => { perDepth[n.depth] = (perDepth[n.depth] || 0) + 1; n.kids.forEach(count); };
    top.forEach(count);
    const R = { 0: 0 };
    Object.keys(perDepth).map(Number).sort((a, b) => a - b).forEach((d) => { R[d] = Math.max((R[d - 1] || 0) + (d === 1 ? 210 : 170), (perDepth[d] * 96) / (2 * Math.PI)); });
    const place = (list, a0, a1) => {
      const total = list.reduce((a, n) => a + weight(n), 0) || 1;
      let a = a0;
      list.forEach((n) => {
        const span = ((a1 - a0) * weight(n)) / total, mid = a + span / 2;
        n.x = Math.cos(mid) * R[n.depth]; n.y = Math.sin(mid) * R[n.depth];
        place(n.kids, a, a + span);
        a += span;
      });
    };
    place(top, -Math.PI / 2, Math.PI * 1.5);
    const all = [], root = { kind: "root", x: 0, y: 0, kids: top, depth: 0 };
    const flat = (n, parent) => { n.parent = parent; all.push(n); n.kids.forEach((k) => flat(k, n)); };
    flat(root, null);
    return all;
  }

  #edge(n) {
    const a = n.parent, col = BRANCH[n.branch % BRANCH.length][1], w = n.kind === "shelf" ? Math.min(9, 2.5 + Math.sqrt(n.s.count)) : 2;
    const mx = (a.x + n.x) / 2, my = (a.y + n.y) / 2, k = 0.18;
    return sv("path", { d: `M${a.x},${a.y} Q${mx - (n.y - a.y) * k},${my + (n.x - a.x) * k} ${n.x},${n.y}`, fill: "none", stroke: col, "stroke-width": w, "stroke-linecap": "round", opacity: 0.55 });
  }

  #chatEdge(n, chatX, cy) {
    const r = bubbleR(n.s.count), x1 = n.x + r, dx = Math.max(60, (chatX - x1) / 2);
    return sv("path", { d: `M${x1},${n.y} C${x1 + dx},${n.y} ${chatX - dx},${cy} ${chatX},${cy}`, fill: "none", stroke: "#4F9FAF", "stroke-width": 3, "stroke-dasharray": "2 9", "stroke-linecap": "round" });
  }

  #label(g, text, x, y, size, weight, anchor) {
    const t = sv("text", { x, y, "text-anchor": anchor || "middle", "font-size": size, "font-weight": weight || 600, class: "mlabel" }, text);
    g.append(t);
    return t;
  }

  #press(g, fn) {
    g.onclick = fn;
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); } };
  }

  #rootNode(memory, sel) {
    const g = sv("g", { class: "mnode bub" + (sel === "" ? " sel" : ""), tabindex: 0, role: "button", "aria-label": `Everything, ${memory.total} notes` }), inner = sv("g", { class: "bubi" });
    inner.append(sv("circle", { r: 62, fill: "url(#g-root)", stroke: "#1A1320", "stroke-width": sel === "" ? 4 : 2.5, filter: "url(#soft)" }));
    this.#label(inner, "My memory", 0, -2, 14, 700);
    this.#label(inner, memory.total + " notes", 0, 17, 12, 500);
    g.append(inner);
    this.#press(g, () => this.on.shelf(""));
    return g;
  }

  #node(n, sel, selFile) {
    if (n.kind === "root") return null;
    const col = BRANCH[n.branch % BRANCH.length];
    if (n.kind === "more") return sv("text", { x: n.x, y: n.y + 4, "text-anchor": "middle", "font-size": 12, fill: "#6B5878" }, `…and ${n.n} more (see the list)`);
    if (n.kind === "file") return this.#fileNode(n, col, selFile);
    const s = n.s, r = bubbleR(s.count), isSel = sel === s.path;
    const g = sv("g", { class: "mnode bub" + (isSel ? " sel" : ""), tabindex: 0, role: "button", "aria-label": `${s.name}, ${s.count} notes` + (s.secret ? `, ${s.secret} secret` : "") }), inner = sv("g", { class: "bubi" });
    g.setAttribute("transform", `translate(${n.x} ${n.y})`);
    g.append(sv("title", {}, s.label || s.name));
    inner.append(sv("circle", { r, fill: `url(#g-${n.branch % BRANCH.length})`, stroke: isSel ? "#1A1320" : col[1], "stroke-width": isSel ? 4 : 2.5, filter: "url(#soft)" }));
    if (s.secret) {  // the red ring shows how much of this shelf is secret
      const c = 2 * Math.PI * (r + 5);
      inner.append(sv("circle", { r: r + 5, fill: "none", stroke: "#D96A62", "stroke-width": 4, "stroke-linecap": "round", "stroke-dasharray": `${c * (s.secret / Math.max(s.count, 1))} ${c}`, transform: "rotate(-90)" }));
    }
    this.#label(inner, String(s.count), 0, 6, 17, 700);
    if (s.has_children) this.#label(inner, this.expanded.has(s.path) ? "▾" : "▸", 0, -r * 0.45, 11, 500);
    this.#label(inner, snip(s.name, 16), 0, r + 22, 15, 700);
    if (s.label) this.#label(inner, snip(s.label, 22), 0, r + 35, 10.5, 400).setAttribute("fill", "#6B5878");
    g.append(inner);
    this.#press(g, () => this.clickShelf(s));
    return g;
  }

  #fileNode(n, col, selFile) {
    const f = n.f, on = selFile === f.id, g = sv("g", { class: "mfile bub pop", tabindex: 0, role: "button", "aria-label": "Note: " + snip(f.text, 60) }), inner = sv("g", { class: "bubi" });
    g.setAttribute("transform", `translate(${n.x} ${n.y})`);
    g.append(sv("title", {}, f.text));
    const text = (f.sensitivity === "low" ? "" : "🔒 ") + (f.long ? "📄 " + snip(f.title, 22) : snip(f.text, 26)), w = Math.max(70, text.length * 6.2 + 20);
    inner.append(sv("rect", { x: -w / 2, y: -15, width: w, height: 30, rx: 15, fill: f.sensitivity === "low" ? "#E6F3EA" : "#F9DDD9", stroke: on ? "#1A1320" : col[1], "stroke-width": on ? 3.5 : 2, filter: "url(#soft)" }));
    this.#label(inner, text, 0, 4, 11, 500);
    g.append(inner);
    this.#press(g, () => this.on.file(f));
    return g;
  }

  #chatPill(c, x, y, color) {
    const g = sv("g", { class: "mchat bub", tabindex: 0, role: "button", "aria-label": "Chat: " + c.title }), inner = sv("g", { class: "bubi" });
    g.setAttribute("transform", `translate(${x} ${y})`);
    inner.append(sv("rect", { x: 0, y: -26, width: 176, height: 52, rx: 26, fill: color, stroke: "#4F9FAF", "stroke-width": 2.5, filter: "url(#soft)" }));
    this.#label(inner, snip(c.title, 20), 88, -2, 12.5, 700);
    this.#label(inner, c.agent.name, 88, 14, 10.5, 400);
    g.append(inner);
    this.#press(g, () => this.on.chat(c.id));
    return g;
  }
}
