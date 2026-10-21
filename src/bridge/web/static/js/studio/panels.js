/* The right-hand side of the studio: change one step, describe the helper, practise, publish and manage, or edit as text.
   Every panel is a function (box, session, ops): `session` is what is open (helper, steps, problems); `ops` are the things a
   panel may ask the studio to do (save a change, select a step, redraw). */
import { el, btn, field, textInput, textArea, numberInput, confirmTwice } from "../lib/dom.js";
import { post } from "../lib/api.js";
import { getState } from "../lib/store.js";
import { cents, plural } from "../lib/format.js";
import { KIND, byId, kindOf, steps, removeStep as removeFromModel } from "./workflow-model.js";

const title = (s) => (KIND[kindOf(s)] || {}).title;
const option = (value, text) => { const o = document.createElement("option"); o.value = value; o.textContent = text; return o; };
const stepChoices = (wf, except, first) => [first, ...steps(wf).filter((x) => x.id !== except).map((x) => [x.id, `${title(x)} (${x.id})`])];

function stepSelect(wf, except, first, value, onChange) {
  const sel = document.createElement("select");
  stepChoices(wf, except, first).forEach(([v, t]) => sel.append(option(v, t)));
  sel.value = value || "";
  sel.onchange = () => onChange(sel.value);
  return sel;
}

/* ---------- one step ---------- */
export function stepPanel(box, S, ops) {
  const wf = S.wf, s = S.sel && byId(wf, S.sel);
  if (!s) {
    const legend = el("div", "legend");
    Object.values(KIND).forEach((k) => { const r = el("div", "small"), sw = el("i", "sw"); sw.style.background = k.fill; r.append(sw, k.title); legend.append(r); });
    box.append(el("p", "small", "Click a step in the picture to change it. Drag a step to move it. Drag the green dot of a step onto another step to say what comes next."), legend,
      el("p", "small muted", "🔒 means a step holds your private files, so it can never be connected to the web. The picture shows this, and the checker enforces it."));
    return;
  }
  const k = KIND[kindOf(s)] || { title: kindOf(s), hint: "" }, edit = (fn) => (v) => { fn(v); ops.changed(["steps"]); };
  box.append(el("h3", "sub", k.title), el("p", "small muted", k.hint), el("p", "small", "Step name: " + s.id));
  if (s.kind === "llm") box.append(field("What should it do? (instructions for the thinking service)", textArea(s.prompt, 7, edit((v) => { s.prompt = v; }))));
  if (s.kind === "tool" && s.tool === "memory_search") box.append(field("What to look for", textInput(s.prompt, edit((v) => { s.prompt = v; }), 300), "{task} means the person's message."));
  if (s.kind === "tool" && s.tool === "web_search") box.append(field("What to search for", textInput(s.prompt, edit((v) => { s.prompt = v; }), 300), "{task} means the person's message. Never put their files here."));
  if (s.kind === "code") box.append(field("The program (runs with no internet)", textArea(s.script, 8, edit((v) => { s.script = v; })), "Leave the answer in a variable called result. Needs the sealed room to be available on this computer."));
  if (s.kind === "gate") box.append(el("p", "small", "Checks that the answer has exactly the fields you described under “Describe”. If it does not, the helper goes to the failure step."));
  if (s.kind !== "return") {
    box.append(field("What comes next", stepSelect(wf, s.id, ["", "(nothing: it ends here)"], s.next, (v) => { if (v) s.next = v; else delete s.next; ops.changed(["steps"]); ops.redrawGraph(); })));
  }
  if (s.kind === "gate") {
    box.append(field("If the check fails, go to", stepSelect(wf, s.id, ["", "(choose)"], s.on_fail, (v) => { if (v) s.on_fail = v; else delete s.on_fail; ops.changed(["steps"]); ops.redrawGraph(); })));
  }
  if (s.kind !== "tool") {
    const fs = el("fieldset", "reads");
    fs.append(el("legend", "small", "What this step may read"));
    [["task", "Your message"], ["history", "The chat so far (private)"], ...steps(wf).filter((x) => x.id !== s.id).map((x) => [x.id, `${title(x)} (${x.id})`])].forEach(([v, t]) => {
      const l = el("label", "small"), c = document.createElement("input");
      c.type = "checkbox"; c.checked = (s.reads || []).includes(v);
      c.onchange = () => { const set = new Set(s.reads || []); c.checked ? set.add(v) : set.delete(v); s.reads = [...set]; ops.changed(["steps"]); ops.redrawGraph(); };
      l.append(c, t);
      fs.append(l);
    });
    box.append(fs);
  }
  if (s.kind === "tool" && s.tool === "memory_search") box.append(el("p", "small muted", "It can only reach the shelves the person opens in their chat."));
  const acts = el("div", "acts");
  acts.append(btn("Make this the first step", "btn", () => { wf.start = s.id; ops.changed(["steps"]); ops.redrawGraph(); }),
    btn("Remove this step", "btn warn", (e) => confirmTwice(e.target, "Really remove?", () => { removeFromModel(wf, s.id); delete S.layout[s.id]; S.sel = null; ops.graphFit(); ops.changed(["steps"]); ops.redrawGraph(); ops.redrawPanel(); })));
  box.append(acts);
}

/* ---------- the description people read before they hire ---------- */
export function aboutPanel(box, S, ops) {
  const m = S.H.manifest, edit = (fn) => (v) => { fn(v); ops.changed(["about"]); };
  box.append(el("p", "small muted", "This is what people read before they hire your helper. Be concrete: the tests show whether it holds up."),
    field("One sentence about it", textArea(m.summary, 2, edit((v) => { m.summary = v; }))),
    field("Best at", textInput(m.speciality, edit((v) => { m.speciality = v; }), 60)),
    field("Version", textInput(m.version, edit((v) => { m.version = v; }), 20), "Like 0.2.0. Raise the first number when it can do more than before."));
  const suite = document.createElement("select");
  [["", "General (sales accounts)"], ...S.list.suites.map((s) => [s.id, s.title])].forEach(([v, t]) => suite.append(option(v, t)));
  suite.value = m.suite || "";
  suite.onchange = () => { if (suite.value) m.suite = suite.value; else delete m.suite; ops.changed(["about"]); };
  box.append(field("It will be tested on", suite, "The tester asks your helper these questions and checks its answers."), el("h3", "sub", "What it can do"));
  (m.skills = m.skills || []).forEach((s, i) => {
    const d = el("div", "skill");
    d.append(field("Skill name", textInput(s.name, edit((v) => { s.name = v; }), 60)), field("What it actually does", textArea(s.does, 2, edit((v) => { s.does = v; }))),
      field("Example questions (one per line)", textArea((s.try_asking || []).join("\n"), 3, edit((v) => { s.try_asking = v.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 3); }))));
    if (m.skills.length > 1) d.append(btn("Remove this skill", "linkbtn", () => { m.skills.splice(i, 1); ops.changed(["about"]); ops.redrawPanel(); }));
    box.append(d);
  });
  if (m.skills.length < 5) box.append(btn("+ Add a skill", "btn", () => { m.skills.push({ name: "", does: "", try_asking: [] }); ops.redrawPanel(); }));
  box.append(el("h3", "sub", "What it cannot do"),
    field("Limits (one per line)", textArea((m.limits || []).join("\n"), 3, edit((v) => { m.limits = v.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5); }))));
  resultEditor(box, m, ops);
}

function resultEditor(box, m, ops) {
  box.append(el("h3", "sub", "What its answer looks like"));
  const schema = m.result_schema || {}, props = schema.properties || {};
  const simple = Object.keys(props).every((k) => { const p = props[k]; return p.type === "string" || p.enum || (p.type === "array" && p.items && p.items.type === "string"); });
  if (!simple) { box.append(el("p", "small muted", "This answer shape is more detailed than this editor can show. Use “Advanced” to change it.")); return; }
  box.append(el("p", "small muted", "Every answer has a summary. Add other fields if you need them; the checker rejects answers that do not match."));
  const rows = el("div", "fieldrows");
  const draw = () => {
    rows.replaceChildren();
    Object.keys(props).forEach((name) => {
      const p = props[name], r = el("div", "frow"), type = p.enum ? "choice" : p.type === "array" ? "list" : "text";
      r.append(el("b", "small", name), el("span", "small muted", type === "choice" ? "one of: " + p.enum.join(", ") : type === "list" ? "a list" : "text"));
      if (name !== "summary") r.append(btn("Remove", "linkbtn", () => { delete props[name]; schema.required = (schema.required || []).filter((x) => x !== name); ops.changed(["about"]); draw(); }));
      rows.append(r);
    });
  };
  draw();
  const name = textInput("", () => {}, 30), type = document.createElement("select"), choices = textInput("", () => {}, 80);
  name.placeholder = "field name";
  [["text", "text"], ["list", "a list of short lines"], ["choice", "one of a few words"]].forEach(([v, t]) => type.append(option(v, t)));
  choices.placeholder = "low, medium, high"; choices.hidden = true;
  type.onchange = () => { choices.hidden = type.value !== "choice"; };
  box.append(rows, el("div", "composerrow"), name, type, choices, btn("Add the field", "btn", () => {
    const key = name.value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_");
    if (!key || props[key]) return;
    props[key] = type.value === "list" ? { type: "array", items: { type: "string", maxLength: 300 }, maxItems: 20 }
      : type.value === "choice" ? { enum: choices.value.split(",").map((x) => x.trim()).filter(Boolean) } : { type: "string", maxLength: 600 };
    if (type.value === "choice" && !props[key].enum.length) { delete props[key]; return; }
    schema.properties = props; m.result_schema = schema; name.value = "";
    ops.changed(["about"]); draw();
  }));
}

/* ---------- practise ---------- */
function showTry(out, r) {
  out.replaceChildren(el("div", "report", r.outcome === "COMPLETE" ? r.answer : r.outcome === "KILLED" ? "The guard stopped this helper. Nothing was delivered." : "No usable answer. " + (r.reasons[0] || "")));
  if (r.files.length) {
    const d = el("details");
    d.append(el("summary", null, "It read " + r.files.length + " of your files"));
    r.files.forEach((f) => d.append(el("div", "small", f.shelf + ": " + f.text)));
    out.append(d);
  } else out.append(el("p", "small muted", "It read none of your files."));
  const how = el("details");
  how.append(el("summary", null, "What it did"));
  r.how.forEach((t) => how.append(el("div", "small", "• " + t)));
  out.append(how);
}

export function tryPanel(box, S, ops) {
  const question = textArea("", 2, () => {});
  question.placeholder = "Ask it something, like a person would.";
  box.append(el("p", "small muted", "A practice run on your own files. Nothing is published and no coins move."), field("Your question", question));
  const fs = el("fieldset", "reads"), out = el("div", "tryout");
  fs.append(el("legend", "small", "Shelves it may open"));
  (getState().memory.shelves || []).filter((s) => s.depth <= 1).forEach((s) => {
    const l = el("label", "small"), c = document.createElement("input");
    c.type = "checkbox"; c.value = s.path;
    l.append(c, "  ".repeat(s.depth) + s.name + " (" + s.count + ")");
    fs.append(l);
  });
  const go = btn("Run it", "btn go2", async () => {
    go.disabled = true;
    out.replaceChildren(el("p", "small muted", "Running…"));
    try {
      const r = await post("/api/studio/try", { id: S.H.id, task: question.value, shelves: [...fs.querySelectorAll("input:checked")].map((c) => c.value) });
      S.lastTry = r;
      showTry(out, r);
      await ops.playPulse(r.visited);
    } catch (e) { out.replaceChildren(el("p", "warnline small", e.message)); }
    go.disabled = false;
  });
  box.append(fs, go, out);
  if (S.lastTry) showTry(out, S.lastTry);
}

/* ---------- publish and manage ---------- */
function chipFor(v) {
  if (v.revoked) return v.status === "suspended" ? ["Taken off the market after a safety incident", "bad"] : ["Retired", "wait"];
  if (v.testing) return ["Being tested…", "wait"];
  if (v.status === "flagged") return ["Caught cheating while tested", "bad"];
  if (v.status === "certified") return [`Trust ${v.score} of 100 (${v.passes} of ${v.total} tests)`, "good"];
  return [v.test_error ? "Testing did not finish" : "Not tested yet", "wait"];
}

const PLANS = [
  ["flat", "One price", "The same price for every answer. Simple and predictable."],
  ["per_file", "By files read", "A starting price plus a few cents for every file the helper reads, up to a maximum. Good when the work grows with the notes."],
  ["per_token", "By thinking used", "A starting price plus cents for every 1,000 tokens the model used, up to a maximum. Good when answers vary a lot in length."],
  ["complexity", "By how hard the question was", "One price for light, standard and deep questions. The platform decides which from what the run did, not from what the helper says."],
  ["monthly", "Monthly plan", "One fee for 30 days and a number of answers. It never renews by itself: the buyer approves each new month."]
];

/** The plan picker: five cards, the fields for the chosen one, and a worked example. Returns {element, pricing()}. */
function planPicker(last) {
  const mode = { v: last.plan || "flat" };
  const num = (v, step, min, max, label) => numberInput(v, { step, min, max, label });
  const f = {
    price: num(last.price_usd || 0.2, 0.05, 0.01, 5, "Price in dollars"), base: num(last.base_usd || 0.05, 0.01, 0, 5, "Starting price in dollars"),
    perFile: num(last.per_file_cents || 3, 1, 1, 500, "Cents for every file it reads"), perTok: num(last.per_1k_tokens_cents || 2, 1, 1, 500, "Cents for every 1,000 tokens"),
    light: num(last.light_cents || 10, 1, 1, 500, "Price of a light question in cents"), standard: num(last.standard_cents || 25, 1, 1, 500, "Price of a standard question in cents"),
    deep: num(last.deep_cents || 60, 1, 1, 500, "Price of a deep question in cents"), monthly: num(last.monthly_usd || 5, 0.5, 0.5, 50, "Monthly fee in dollars"),
    included: num(last.included_answers || 100, 1, 1, 1000, "Answers included each month")
  };
  const wrap = el("div"), cards = el("div", "plans"), fields = el("div"), preview = el("p", "small preview");
  const cts = (x) => Math.round(parseFloat(x.value) * 100) || 0, int = (x) => parseInt(x.value, 10) || 0;
  const drawPreview = () => {
    const cap = cts(f.price);
    preview.textContent = {
      flat: `Every answer costs ${cap}¢.`,
      per_file: `An answer that reads 4 files costs ${Math.min(cap, cts(f.base) + 4 * int(f.perFile))}¢. The buyer sees the maximum (${cap}¢) before starting and pays only for what was read.`,
      per_token: `An answer that uses 2,000 tokens costs ${Math.min(cap, cts(f.base) + 2 * int(f.perTok))}¢. The buyer sees the maximum (${cap}¢) first and pays only for what was used.`,
      complexity: `Light ${int(f.light)}¢, standard ${int(f.standard)}¢, deep ${int(f.deep)}¢. Deep means it ran a program, thought three or more times, or read 12 or more files. Standard means it thought twice, searched the web, or read 4 or more files. The buyer sees the deepest price first.`,
      monthly: `The buyer pays $${(parseFloat(f.monthly.value) || 0).toFixed(2)} once and can ask up to ${int(f.included)} answers in 30 days. There is no automatic renewal.`
    }[mode.v];
  };
  const drawFields = () => {
    fields.replaceChildren();
    ({
      flat: [["Price per answer (US dollars)", f.price]],
      per_file: [["Starting price (US dollars)", f.base], ["Cents for every file it reads", f.perFile], ["Most one answer can cost (US dollars)", f.price]],
      per_token: [["Starting price (US dollars)", f.base], ["Cents for every 1,000 tokens", f.perTok], ["Most one answer can cost (US dollars)", f.price]],
      complexity: [["Light question (cents)", f.light], ["Standard question (cents)", f.standard], ["Deep question (cents)", f.deep]],
      monthly: [["Monthly fee (US dollars)", f.monthly], ["Answers included", f.included]]
    })[mode.v].forEach(([t, x]) => fields.append(field(t, x)));
    fields.append(preview);
    drawPreview();
    Object.values(f).forEach((x) => { x.oninput = drawPreview; });
  };
  PLANS.forEach(([v, t, d]) => {
    const l = el("label", "plancard" + (mode.v === v ? " on" : "")), r = document.createElement("input"), body = el("div");
    r.type = "radio"; r.name = "pricemode"; r.value = v; r.checked = mode.v === v;
    r.onchange = () => { mode.v = v; cards.querySelectorAll(".plancard").forEach((c) => c.classList.toggle("on", c.firstChild.value === v)); drawFields(); };
    body.append(el("b", null, t), el("div", "small muted", d));
    l.append(r, body);
    cards.append(l);
  });
  drawFields();
  wrap.append(cards, fields);
  return {
    element: wrap,
    pricing: () => ({
      flat: { plan: "flat", price_usd: parseFloat(f.price.value) },
      per_file: { plan: "per_file", price_usd: parseFloat(f.price.value), base_usd: parseFloat(f.base.value) || 0, per_file_cents: int(f.perFile) },
      per_token: { plan: "per_token", price_usd: parseFloat(f.price.value), base_usd: parseFloat(f.base.value) || 0, per_1k_tokens_cents: int(f.perTok) },
      complexity: { plan: "complexity", light_cents: int(f.light), standard_cents: int(f.standard), deep_cents: int(f.deep) },
      monthly: { plan: "monthly", monthly_usd: parseFloat(f.monthly.value), included_answers: int(f.included) }
    })[mode.v]
  };
}

export function publishPanel(box, S, ops) {
  const m = S.H.manifest, last = S.H.versions[0] || {}, problems = S.problems;
  box.append(el("p", "small", `Publishing puts version ${m.version} on the market with your signature. A tester then runs it on a fixed set of questions and tries to catch it cheating. Its trust score comes from that, not from you.`));
  if (problems.length) box.append(el("p", "small warnline", "Fix the " + plural(problems.length, "thing") + " listed at the top first."));
  const plan = planPicker(last), mail = textInput(last.payout_email || "", () => {}, 120);
  mail.placeholder = "you@example.com (optional)";
  box.append(plan.element, el("p", "small muted", "Demo money only: nothing real moves in this demo."), field("Where you would be paid", mail));
  const go = btn("Publish version " + m.version, "btn go2", async () => {
    go.disabled = true;
    try {
      await post("/api/studio/publish", { id: S.H.id, payout_email: mail.value, ...plan.pricing() });
      ops.note("Published. The tester is checking it now; this can take a few minutes.");
      await ops.reopen("publish");
    } catch (e) { ops.note(e.message); go.disabled = false; }
  });
  go.disabled = problems.length > 0;
  box.append(go, el("h3", "sub", "Your versions"));
  if (!S.H.versions.length) box.append(el("p", "small muted", "Nothing published yet."));
  S.H.versions.forEach((v) => {
    const c = el("div", "mem"), [text, cls] = chipFor(v), acts = el("div", "acts");
    c.append(el("div", null, "Version " + v.version), el("span", "tag " + cls, text),
      el("div", "small muted", `${plural(v.answers, "answer")} given · earned ${cents(v.earned_cents)} · ${plural(v.stars, "fan")} · ${v.price_text}`));
    if (v.test_error) c.append(el("div", "small warnline", v.test_error));
    if (!v.revoked) {
      acts.append(
        btn("Test it again", "btn", async () => { try { await post("/api/studio/retest", { key: v.key }); await ops.reopen("publish"); } catch (e) { ops.note(e.message); } }),
        btn("Change price", "btn", async () => { try { await post("/api/studio/price", { key: v.key, payout_email: mail.value, ...plan.pricing() }); await ops.reopen("publish"); } catch (e) { ops.note(e.message); } }),
        btn("Take it off the market", "btn warn", (e) => confirmTwice(e.target, "Really?", async () => { try { await post("/api/studio/retire", { key: v.key }); await ops.reopen("publish"); } catch (er) { ops.note(er.message); } })));
    }
    c.append(acts);
    box.append(c);
  });
  box.append(el("h3", "sub", "Delete this draft"), btn("Delete the draft", "btn warn", (e) => confirmTwice(e.target, "Really delete?", async () => {
    try { await post("/api/studio/delete", { id: S.H.id }); await ops.afterDelete(); } catch (er) { ops.note(er.message); }
  })));
}

/* ---------- power users: the steps as text ---------- */
export function textPanel(box, S, ops) {
  const t = textArea(S.H.workflow_text, 18, () => {}, 30000);
  t.className = "mono";
  box.append(el("p", "small muted", "The steps as written in the file. Changes here replace the picture once they are valid."), t,
    btn("Use this text", "btn go2", async () => {
      try { await ops.saveText(t.value); } catch (e) { ops.note(e.message); }
    }));
}

export const PANELS = { steps: stepPanel, about: aboutPanel, try: tryPanel, publish: publishPanel, text: textPanel };
