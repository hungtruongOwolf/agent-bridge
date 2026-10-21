/* The shape of a helper's steps (its "workflow"), as plain functions on a plain object. No DOM here, so it is tested with node.

   wf = { name, start, budget, steps: [ {id, kind, next, on_fail, reads, prompt, tool, tools, memory, ...} ] } */

export const NODE = { w: 190, h: 74, gx: 80, gy: 40 };

export const KIND = {
  memory_search: { title: "Look through your files", fill: "#D2E7DA", hint: "Reads files from the shelves the person opened. Nothing else." },
  web_search: { title: "Look up the web", fill: "#F3DACA", hint: "Searches public pages. It can never be given your files." },
  llm: { title: "Think", fill: "#CFE5E9", hint: "Asks the thinking service to write something from what it was given." },
  gate: { title: "Check the answer", fill: "#F3E4BC", hint: "Stops a bad answer before it goes on." },
  code: { title: "Run a small program", fill: "#E0DAF2", hint: "Runs your own code in a sealed room with no internet." },
  return: { title: "Hand over the answer", fill: "#F3D3CD", hint: "The guard inspects this before it reaches the person." }
};

export const kindOf = (s) => (s.kind === "tool" ? s.tool : s.kind);
export const steps = (wf) => (wf && Array.isArray(wf.steps) ? wf.steps : []);
export const byId = (wf, id) => steps(wf).find((s) => s.id === id);
export const nameOf = (wf, id) => { const s = byId(wf, id); return s ? ((KIND[kindOf(s)] || {}).title || kindOf(s)) + " (" + id + ")" : id; };

/** How far each step is from the start (so the picture reads left to right), and the order they are drawn in. */
export function depths(wf) {
  const d = {}, order = [], first = wf && wf.start;
  if (!first || !byId(wf, first)) return { d, order };
  d[first] = 0;
  order.push(first);
  for (const id of order) {
    const s = byId(wf, id);
    [s.next, s.on_fail].forEach((t) => { if (t && byId(wf, t) && !(t in d)) { d[t] = d[id] + 1; order.push(t); } });
  }
  const n = steps(wf).length;
  for (let i = 0; i < n; i++) {  // a step sits to the right of everything that leads to it
    for (const id of order) {
      const s = byId(wf, id);
      [s.next, s.on_fail].forEach((t) => { if (t && byId(wf, t) && d[t] <= d[id] && !(d[t] > n)) d[t] = d[id] + 1; });
    }
  }
  steps(wf).forEach((s) => { if (!(s.id in d)) { d[s.id] = 0; order.push(s.id); } });  // steps nothing leads to still appear
  return { d, order };
}

/** Steps that hold the person's private data: the ones that read the memory shelves, and everything that reads those. */
export function privateSet(wf) {
  const p = new Set(steps(wf).filter((s) => s.memory === "lens").map((s) => s.id));
  p.add("history");
  for (let changed = true; changed;) {
    changed = false;
    steps(wf).forEach((s) => { if (!p.has(s.id) && (s.reads || []).some((r) => p.has(r))) { p.add(s.id); changed = true; } });
  }
  return p;
}

/** Where each step is drawn: a saved position, or a column by depth and a row within the column. */
export function place(wf, layout) {
  const { d, order } = depths(wf), rows = {}, out = {};
  order.forEach((id) => {
    const col = d[id];
    rows[col] = (rows[col] === undefined ? -1 : rows[col]) + 1;
    out[id] = (layout && layout[id]) || { x: 150 + col * (NODE.w + NODE.gx), y: 40 + rows[col] * (NODE.h + NODE.gy) };
  });
  return out;
}

/** The steps you reach by following "next" from the start. */
export function mainPath(wf) {
  const seen = new Set(), order = [];
  let cur = wf && wf.start;
  while (cur && byId(wf, cur) && !seen.has(cur)) { seen.add(cur); order.push(byId(wf, cur)); cur = byId(wf, cur).next; }
  return order;
}

/** The last working step before the check or the hand-over: new steps go after it. */
export const lastOnMainPath = (wf) => mainPath(wf).filter((x) => x.kind !== "return" && x.kind !== "gate").pop() || null;

function newId(wf, base) {
  let i = 1;
  while (byId(wf, base + (i > 1 ? i : ""))) i++;
  return base + (i > 1 ? i : "");
}

const lastThinkId = (wf) => (steps(wf).filter((s) => s.kind === "llm").pop() || {}).id;

const TEMPLATES = {
  files: (id) => ({ id, kind: "tool", tool: "memory_search", tools: ["memory_search"], memory: "lens", prompt: "{task}" }),
  web: (id) => ({ id, kind: "tool", tool: "web_search", tools: ["web_search"], prompt: "{task}" }),
  think: (id) => ({ id, kind: "llm", reads: ["task", "history"], prompt: "Answer the question in INPUTS.task using only what is in the other inputs. Reply as JSON with the key summary: at most 3 plain sentences." }),
  check: (id, wf) => ({ id, kind: "gate", check: "result_matches_schema", reads: [lastThinkId(wf)].filter(Boolean) }),
  program: (id) => ({ id, kind: "code", script: "result = {\"summary\": \"ok\"}\n", reads: [] }),
  deliver: (id, wf) => ({ id, kind: "return", reads: [lastThinkId(wf)].filter(Boolean) })
};
const BASE_ID = { files: "read", web: "web", think: "think", check: "check", program: "program", deliver: "done" };

/**
 * Add a step of `kind` and join it to the others where it belongs. `selected` is the id of the step the person has open.
 * Something to read or look up goes before the step that thinks (which then reads it); a check goes after the last thinking step;
 * a hand-over joins the first check that has nowhere to go on failure. Returns the new step.
 */
export function addStep(wf, kind, selected) {
  const s = TEMPLATES[kind](newId(wf, BASE_ID[kind]), wf);
  if (kind === "files" || kind === "web") {
    const order = mainPath(wf), at = order.findIndex((x) => x.kind === "llm");
    if (at >= 0) {
      const target = order[at], prev = order[at - 1];
      if (prev) prev.next = s.id; else wf.start = s.id;
      s.next = target.id;
      target.reads = [...new Set([...(target.reads || []), s.id])];
      wf.steps.push(s);
      return s;
    }
  }
  const lastThink = mainPath(wf).filter((x) => x.kind === "llm").pop();
  const open = selected && byId(wf, selected);
  const after = kind === "check" ? lastThink || open || lastOnMainPath(wf) : open || lastOnMainPath(wf);
  if (after && after.kind !== "return" && s.kind !== "return") {
    s.next = after.next;
    if (s.kind === "gate") {
      const bad = steps(wf).find((x) => x.kind === "return" && !(x.reads || []).length);
      s.on_fail = after.on_fail || (bad && bad.id) || undefined;
    }
    after.next = s.id;
  }
  if (kind === "deliver") {
    const gate = steps(wf).find((x) => x.kind === "gate" && !x.on_fail);
    if (gate) gate.on_fail = s.id;
  } else if (s.kind !== "return") {
    const end = steps(wf).find((x) => x.kind === "return");
    if (end) s.next = end.id;
  }
  wf.steps.push(s);
  if (!wf.start) wf.start = s.id;
  return s;
}

/** Remove a step and mend the arrows that pointed at it. */
export function removeStep(wf, id) {
  const s = byId(wf, id);
  if (!s) return;
  wf.steps = wf.steps.filter((x) => x.id !== id);
  wf.steps.forEach((x) => {
    if (x.next === id) { if (s.next && s.next !== x.id) x.next = s.next; else delete x.next; }
    if (x.on_fail === id) delete x.on_fail;
    x.reads = (x.reads || []).filter((r) => r !== id);
    if (x.propose === id) delete x.propose;
  });
  if (wf.start === id) wf.start = s.next || (wf.steps[0] && wf.steps[0].id);
}

/** The checker's words, in plain language, and which step they are about: [stepId | null, text]. */
export function plainProblem(wf, p) {
  let m;
  if ((m = /step '([a-z0-9_]+)' is unreachable from start/.exec(p))) return [m[1], `“${nameOf(wf, m[1])}” is not connected: nothing leads to it. Drag the green dot of an earlier step onto it, or remove it.`];
  if ((m = /step '([a-z0-9_]+)': (.*)/.exec(p))) {
    const text = m[2].replace(/`/g, "").replace(/'([a-z0-9_]+)'/g, (x, id) => (byId(wf, id) ? `“${nameOf(wf, id)}”` : x))
      .replace("which never runs before it", "which only runs later. Move it after that step, or untick it below.");
    return [m[1], `“${nameOf(wf, m[1])}”: ${text}`];
  }
  if ((m = /cycle through step '([a-z0-9_]+)'/.exec(p))) return [m[1], `The steps go round in a circle at “${nameOf(wf, m[1])}”. Loops are not available yet.`];
  return [null, p.replace(/^The steps: /, "")];
}
