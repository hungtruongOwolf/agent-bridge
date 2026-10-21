/* A helper's steps as a picture you can touch: drag a step, drag its green dot onto the next step, click to open it.
   Zoom and move like a map. The model (what the steps are) lives in workflow-model.js; this file only draws and listens. */
import { sv } from "../lib/dom.js";
import { PanZoom } from "../lib/panzoom.js";
import { KIND, NODE, byId, kindOf, place, privateSet, steps } from "./workflow-model.js";

const { w: NW, h: NH } = NODE;

export class StepGraph {
  /** on: { select(id), changed(what) } */
  constructor(svg, on) {
    this.svg = svg;
    this.on = on;
    this.pz = new PanZoom(svg, { skip: ".node,.pill", min: 0.3, maxFit: 1.1 });
    this.state = { wf: null, layout: {}, sel: null, problems: [], pulse: [], showData: true };
    this.fitNext = true;
  }

  set(patch) { this.state = { ...this.state, ...patch }; }

  #hasProblem(id) { return this.state.problems.some((p) => new RegExp("step '" + id + "'").test(p)); }

  draw() {
    const { wf, layout, sel, pulse, showData } = this.state, svg = this.svg;
    svg.replaceChildren();
    if (!wf || !steps(wf).length) {
      svg.append(sv("text", { x: 20, y: 40, fill: "#6B5878" }, "The steps could not be read. Fix the text under “Advanced”, or start again from a template."));
      return;
    }
    const P = place(wf, layout), priv = privateSet(wf);
    P.task = { x: 14, y: 30 };
    P.history = { x: 14, y: 130 };
    const defs = sv("defs");
    [["arr", "#1A1320"], ["arrfail", "#D96A62"], ["arrdata", "#A899B5"]].forEach(([id, col]) => {
      const m = sv("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
      m.append(sv("path", { d: "M0,0 L10,5 L0,10 z", fill: col }));
      defs.append(m);
    });
    const shadow = sv("filter", { id: "gsoft", x: "-20%", y: "-20%", width: "140%", height: "150%" });
    shadow.append(sv("feDropShadow", { dx: 0, dy: 3, stdDeviation: 3.5, "flood-color": "#3D2E4A", "flood-opacity": 0.22 }));
    defs.append(shadow);
    const vp = sv("g"), edges = sv("g"), nodes = sv("g");
    vp.append(edges, nodes);
    svg.append(defs, vp);
    let w = 600, h = 300;
    Object.values(P).forEach((p) => { w = Math.max(w, p.x + NW + 40); h = Math.max(h, p.y + NH + 40); });

    [["task", "Your message"], ["history", "Chat so far"]].forEach(([id, label]) => {
      const p = P[id], g = sv("g", { class: "pill" });
      g.append(sv("rect", { x: p.x, y: p.y, width: 104, height: 26, rx: 13, fill: id === "history" ? "#FFF8E7" : "#CFE5E9", stroke: "#1A1320", "stroke-width": 2 }),
        sv("text", { x: p.x + 52, y: p.y + 17, "text-anchor": "middle", "font-size": 11 }, label));
      nodes.append(g);
    });

    const edge = (a, b, cls, marker, dy) => {
      const A = P[a], T = P[b];
      if (!A || !T) return;
      const input = a === "task" || a === "history";
      const x1 = input ? A.x + 104 : A.x + NW, y1 = input ? A.y + 13 : A.y + (cls === "fail" ? NH : NH / 2);
      const x2 = T.x, y2 = T.y + NH / 2 + (dy || 0), off = Math.max(40, Math.abs(x2 - x1) / 2);
      edges.append(sv("path", { d: `M${x1},${y1} C${x1 + off},${cls === "fail" ? y1 + 50 : y1} ${x2 - off},${y2} ${x2},${y2}`, class: "edge " + cls, "marker-end": `url(#${marker})`, fill: "none" }));
    };
    steps(wf).forEach((s) => {
      if (s.next) edge(s.id, s.next, "next", "arr");
      if (s.on_fail) edge(s.id, s.on_fail, "fail", "arrfail");
      if (showData) (s.reads || []).forEach((r, i) => { if (byId(wf, r) || r === "task" || r === "history") edge(r, s.id, "data", "arrdata", -14 + i * 7); });
    });

    steps(wf).forEach((s) => nodes.append(this.#node(s, P[s.id], priv.has(s.id), sel === s.id, this.#hasProblem(s.id), pulse.includes(s.id))));
    this.pz.setViewport(vp, { w, h });
    if (this.fitNext) { this.fitNext = false; this.pz.fitSoon(); }
  }

  #node(s, p, isPrivate, selected, bad, pulsing) {
    const k = KIND[kindOf(s)] || { title: kindOf(s), fill: "#F4E9C7", hint: "" };
    const g = sv("g", { class: "node" + (selected ? " sel" : "") + (bad ? " bad" : "") + (pulsing ? " pulse" : ""), tabindex: 0, role: "button", "aria-label": `${k.title} (${s.id})` + (isPrivate ? ", holds private data" : "") });
    g.setAttribute("transform", `translate(${p.x},${p.y})`);
    g.append(sv("title", {}, k.hint),
      sv("rect", { width: NW, height: NH, rx: 16, fill: k.fill, stroke: "#1A1320", "stroke-width": selected ? 3.5 : 2, filter: "url(#gsoft)" }),
      sv("text", { x: 14, y: 27, "font-size": 14, "font-weight": 700 }, k.title),
      sv("text", { x: 14, y: 46, "font-size": 11.5, fill: "#3D2E4A" }, s.id));
    if (isPrivate && s.kind !== "return") g.append(sv("text", { x: 14, y: 63, "font-size": 10.5, fill: "#9a3a33" }, "🔒 holds your private data"));
    else if (s.tool === "web_search") g.append(sv("text", { x: 14, y: 63, "font-size": 10.5, fill: "#6B5878" }, "public"));
    if (s.kind !== "return") {
      g.append(this.#port(s.id, "next", NW, NH / 2, "#5CA97A", "Drag to the next step"));
      if (s.kind === "gate") g.append(this.#port(s.id, "on_fail", NW / 2, NH, "#D96A62", "Drag to where it goes if the check fails"));
    }
    g.addEventListener("pointerdown", (e) => this.#drag(e, s.id));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.on.select(s.id); } });
    return g;
  }

  #port(id, kind, cx, cy, fill, hint) {
    const c = sv("circle", { cx, cy, r: 7, fill, stroke: "#1A1320", "stroke-width": 2, class: "port" });
    c.append(sv("title", {}, hint));
    c.addEventListener("pointerdown", (e) => this.#link(e, id, kind));
    return c;
  }

  #drag(e, id) {
    if (e.target.classList && e.target.classList.contains("port")) return;
    e.preventDefault();
    const { wf, layout } = this.state, P = place(wf, layout), p0 = this.pz.toDrawing(e), origin = { ...P[id] };
    let moved = false;
    const move = (ev) => {
      const q = this.pz.toDrawing(ev);
      if (Math.abs(q.x - p0.x) + Math.abs(q.y - p0.y) > 4) moved = true;
      if (moved) { layout[id] = { x: Math.max(0, Math.round(origin.x + q.x - p0.x)), y: Math.max(0, Math.round(origin.y + q.y - p0.y)) }; this.draw(); }
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (moved) this.on.changed(["layout"]); else this.on.select(id);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  #link(e, from, kind) {
    e.preventDefault();
    e.stopPropagation();
    const { wf, layout } = this.state, P = place(wf, layout), a = P[from];
    const x1 = kind === "next" ? a.x + NW : a.x + NW / 2, y1 = kind === "next" ? a.y + NH / 2 : a.y + NH;
    const line = sv("line", { x1, y1, x2: x1, y2: y1, stroke: kind === "next" ? "#5CA97A" : "#D96A62", "stroke-width": 3, "stroke-dasharray": "6 4" });
    this.pz.vp.append(line);
    const move = (ev) => { const q = this.pz.toDrawing(ev); line.setAttribute("x2", q.x); line.setAttribute("y2", q.y); };
    const up = (ev) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      line.remove();
      const q = this.pz.toDrawing(ev);
      const hit = steps(wf).find((s) => s.id !== from && P[s.id] && q.x >= P[s.id].x && q.x <= P[s.id].x + NW && q.y >= P[s.id].y && q.y <= P[s.id].y + NH);
      if (hit) { byId(wf, from)[kind] = hit.id; this.on.changed(["steps"]); this.draw(); }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
}
