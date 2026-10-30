/* My helpers: build, test, publish and manage your own helpers.
       /helpers              the list (opens the first helper)
       /helpers/<name>       a helper's steps, as a picture
       /helpers/<name>/<tab> about | try | publish | text
   The steps are drawn as a graph you can touch; the server checks every change and says in plain words what is wrong. */
import { $, el, btn, debounce } from "../lib/dom.js";
import { get, post, url } from "../lib/api.js";
import { refresh } from "../lib/store.js";
import { navigate, paths } from "../lib/nav.js";
import { plural, niceName } from "../lib/format.js";
import { toast } from "../lib/toast.js";
import { StepGraph } from "../studio/graph.js";
import { PANELS } from "../studio/panels.js";
import { addStep, byId, plainProblem } from "../studio/workflow-model.js";

const TABS = ["steps", "about", "try", "publish", "text"];
const S = { list: null, H: null, wf: null, sel: null, layout: {}, problems: [], dirty: false, lastTry: null, tab: "steps", pulse: [], showData: true };
let graph = null, pollTimer = null;

const note = (t) => { if (t) toast(t, !/^(Published|Saved)/.test(t)); };

/* ---------- the list on the left ---------- */
async function loadList() { S.list = await get("/api/studio"); }

function drawList() {
  const box = $("helperlist");
  box.replaceChildren();
  S.list.helpers.forEach((h) => {
    const a = el("a", "threadbtn" + (S.H && S.H.id === h.id ? " cur" : "")), live = h.versions.find((v) => !v.revoked);
    a.href = paths.studio(h.id);
    a.dataset.link = "";
    a.append(el("span", "name", h.title), el("span", "blurb", h.problems ? plural(h.problems, "thing") + " to fix" : live ? "On the market: v" + live.version : "Draft v" + h.version));
    box.append(a);
  });
  if (!S.list.helpers.length) box.append(el("p", "empty", "You have not built a helper yet."));
  $("newbox").open = !S.list.helpers.length;  // with no helper yet the form is the first thing to see
  $("newtemplate").replaceChildren(...S.list.templates.map((x) => { const o = document.createElement("option"); o.value = x.id; o.textContent = x.title; return o; }));
}

async function createHelper(ev) {
  ev.preventDefault();
  try {
    const h = await post("/api/studio/create", { id: $("newname").value.trim().toLowerCase().replace(/\s+/g, "-"), template: $("newtemplate").value });
    $("newname").value = "";
    await loadList();
    navigate(paths.studio(h.id));
  } catch (e) { note(e.message); }
}

/* ---------- opening a helper ---------- */
async function openHelper(id) {
  S.H = await get(url("/api/studio/helper", { id }));
  S.wf = S.H.workflow ? JSON.parse(JSON.stringify(S.H.workflow)) : null;
  S.layout = S.H.layout || {};
  S.problems = S.H.problems;
  S.sel = null; S.lastTry = null; S.pulse = []; S.dirty = false;
  graph.fitNext = true;
}

function drawTitle() {
  $("helpertitle").textContent = `${niceName(S.H.id)}  ·  version ${S.H.manifest.version || "?"}`;
}

function drawProblems() {
  const box = $("problems");
  box.replaceChildren();
  if (!S.problems.length) { box.append(el("p", "small okline", S.dirty ? "Saving…" : "✓ Everything checks out. This helper is ready to practise or publish.")); return; }
  box.append(el("p", "small warnline", plural(S.problems.length, "thing") + " to fix before it can be published:"));
  const ul = el("ul", "small probs");
  S.problems.slice(0, 6).forEach((p) => {
    const [id, text] = plainProblem(S.wf, p), li = el("li");
    if (id && byId(S.wf, id)) { const b = btn(text, "linkbtn probbtn", () => select(id)); b.title = "Show this step"; li.append(b); } else li.append(text);
    ul.append(li);
  });
  box.append(ul);
}

function redrawGraph() {
  graph.set({ wf: S.wf, layout: S.layout, sel: S.sel, problems: S.problems, pulse: S.pulse, showData: S.showData });
  graph.draw();
}

const ops = {
  changed,
  redrawGraph,
  redrawPanel: drawPanel,
  graphFit: () => { graph.fitNext = true; },
  note,
  playPulse: async (ids) => { for (const id of ids) { S.pulse = [id]; redrawGraph(); await new Promise((r) => setTimeout(r, 450)); } S.pulse = []; redrawGraph(); },
  reopen: async (tab) => { await refresh(); await loadList(); await openHelper(S.H.id); navigate(paths.studio(S.H.id, tab), { replace: true }); },
  afterDelete: async () => { S.H = null; await loadList(); navigate(paths.studio(), { replace: true }); },
  saveText: async (text) => {
    const r = await post("/api/studio/save", { id: S.H.id, workflow_text: text });
    S.H.workflow_text = r.workflow_text; S.wf = r.workflow; S.problems = r.problems; S.sel = null;
    drawProblems(); redrawGraph();
  }
};

function drawPanel() {
  TABS.forEach((t) => { const b = $("ptab-" + t); b.setAttribute("aria-selected", String(S.tab === t)); });
  const box = $("panelbody");
  box.replaceChildren();
  PANELS[S.tab](box, S, ops);
}

function select(id) {
  S.sel = id;
  if (S.tab !== "steps") { navigate(paths.studio(S.H.id)); return; }
  redrawGraph();
  drawPanel();
}

/* ---------- saving: a moment after the last change, the server checks it and says what is wrong ---------- */
const saveSoon = debounce((what) => save(what), 500);

function changed(what) {
  S.dirty = true;
  drawProblems();
  saveSoon(what);
}

async function save(what) {
  if (!S.H) return;
  const body = { id: S.H.id, layout: S.layout };
  if (!what || what.includes("steps")) body.workflow = S.wf;
  if (!what || what.includes("about")) body.manifest = S.H.manifest;
  try {
    const r = await post("/api/studio/save", body);
    S.dirty = false; S.problems = r.problems; S.H.caps = r.caps; S.H.versions = r.versions;
    drawProblems();
    if (S.tab === "publish") drawPanel();
  } catch (e) { note(e.message); }
}

/* ---------- a version being tested: look again every few seconds until it is done ---------- */
function watchTests() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (!S.H || !S.H.versions.some((v) => v.testing)) return;
    try {
      const r = await get(url("/api/studio/helper", { id: S.H.id }));
      S.H.versions = r.versions;
      if (!r.versions.some((v) => v.testing)) await refresh();
      if (S.tab === "publish") drawPanel();
    } catch (e) { /* the next look tries again */ }
  }, 3000);
}

function showHelper() {
  $("studiopanel").hidden = false;
  $("studiomain").hidden = false;
  $("studioempty").hidden = true;
  drawList(); drawTitle(); drawProblems(); redrawGraph(); drawPanel();
}

export const studioView = {
  section: "view-studio",

  mount() {
    graph = new StepGraph($("graph"), { select: (id) => select(id), changed });
    graph.pz.bindButtons($("gzoomin"), $("gzoomout"), $("gfit"));
    $("newform").onsubmit = createHelper;
    TABS.forEach((t) => { $("ptab-" + t).onclick = () => navigate(paths.studio(S.H && S.H.id, t)); });
    [["addfiles", "files"], ["addweb", "web"], ["addthink", "think"], ["addcheck", "check"], ["addprogram", "program"], ["adddeliver", "deliver"]].forEach(([id, kind]) => {
      $(id).onclick = () => {
        if (!S.wf) return;
        const s = addStep(S.wf, kind, S.sel);
        S.sel = s.id;
        graph.fitNext = true;
        changed(["steps"]); redrawGraph(); drawPanel();
      };
    });
    $("tidy").onclick = () => { S.layout = {}; graph.fitNext = true; changed(["layout"]); redrawGraph(); };
    $("showdata").onchange = (e) => { S.showData = e.target.checked; redrawGraph(); };
  },

  async enter({ id, tab }) {
    try { if (!S.list) await loadList(); } catch (e) { note(e.message); return; }
    S.tab = TABS.includes(tab) ? tab : "steps";
    if (!id) {
      const first = S.list.helpers[0];
      if (first) { navigate(paths.studio(first.id), { replace: true }); return; }
      S.H = null; drawList();
      $("studiopanel").hidden = true;
      $("studiomain").hidden = true;
      $("studioempty").hidden = false;
      return;
    }
    if (!S.H || S.H.id !== id) {
      try { await openHelper(id); } catch (e) { note(e.message); navigate(paths.studio(), { replace: true }); return; }
    }
    showHelper();
    watchTests();
  },

  leave() { clearInterval(pollTimer); },

  redraw() {}
};
