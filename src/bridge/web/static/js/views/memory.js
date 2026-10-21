/* My memory: a map of shelves (zoom, drag, click), and next to it the notes of the shelf you opened. Every state has an address:
       /memory                 everything
       /memory/shelf/work/x    one shelf and what lies below it
       /memory/note/<id>       one note, shown in full
       /memory/trash           deleted notes waiting 30 days */
import { $, el, btn, confirmTwice, debounce } from "../lib/dom.js";
import { get, post, url } from "../lib/api.js";
import { getState, refresh } from "../lib/store.js";
import { navigate, paths } from "../lib/nav.js";
import { plural, pretty, month } from "../lib/format.js";
import { say, toast } from "../lib/toast.js";
import { MemoryMap } from "../components/memory-map.js";
import { noteCard } from "../components/note-card.js";
import { drawProposals } from "../components/proposals.js";
import { setupMemoryForms } from "../components/memory-forms.js";
import { openAdd } from "../components/add-dialog.js";

const PAGE = 30;
let map = null;
let sel = "", selFile = null, trash = false, leaf = [], stalls = [];
let offset = 0, query = "", selecting = false;
const picked = new Set();

const shelves = () => (getState().memory ? getState().memory.shelves : []);

/* ---------- the map ---------- */
async function loadChats() {
  const had = stalls.length;
  try { stalls = (await get("/api/office")).stalls; } catch (e) { stalls = []; }
  if (stalls.length !== had) map.fitNext = true;
  drawMap();
}

function drawMap() {
  map.set({ memory: getState().memory, shelves: shelves(), sel, selFile, leaf, stalls });
  map.draw();
  const list = $("shelfnames");
  list.replaceChildren(...shelves().map((s) => { const o = document.createElement("option"); o.value = s.path; return o; }));
}

function drawStats() {
  const m = getState().memory, parts = [plural(m.total, "note")];
  if (m.long) parts.push(m.long + " long");
  if (m.contacts) parts.push(plural(m.contacts, "person", "people"));
  if (m.secret) parts.push(m.secret + " secret");
  $("memstats").textContent = parts.join(" · ") + (m.oldest ? ` · written ${month(m.oldest)} to ${month(m.newest)}` : "") + ". Scroll to zoom, drag the background to move.";
}

/* ---------- the shelf's own actions ---------- */
function drawShelfActions() {
  const box = $("shelfactions");
  box.replaceChildren();
  $("shelftitle").textContent = trash ? "Trash" : sel ? `Notes on “${pretty(sel)}” and below` : "All notes";
  if (trash) return;
  const s = shelves().find((x) => x.path === sel);
  box.append(btn(sel ? "+ Add a note here" : "+ Add a note", "btn go2 sm", () => openAdd({ shelf: sel })),
             btn(sel ? "+ New shelf inside" : "+ New shelf", "btn sm", () => openAdd({ shelf: sel, newShelf: true })));
  if (!sel || !s) return;
  const form = el("div", "shelfform");
  box.append(btn("Rename or move", "btn sm", () => shelfForm(form, "move")), btn(s.label ? "Change its description" : "Describe this shelf", "btn sm", () => shelfForm(form, "note")), form);
}

function shelfForm(form, kind) {
  form.replaceChildren();
  const s = shelves().find((x) => x.path === sel), input = document.createElement("input");
  input.type = "text"; input.maxLength = 200;
  input.value = kind === "move" ? sel : s ? s.label : "";
  input.setAttribute("aria-label", kind === "move" ? "New shelf path" : "A short note about this shelf");
  const save = btn("Save", "btn go2", async () => {
    try {
      if (kind === "move") {
        const r = await post("/api/memory", { action: "move_shelf", from: sel, to: input.value });
        say("Moved " + plural(r.moved, "note") + ".");
        await refresh();
        navigate(paths.shelf(input.value.trim().toLowerCase().replace(/\s*\/\s*/g, "/")), { replace: true });
      } else {
        await post("/api/memory", { action: "shelf_note", shelf: sel, text: input.value });
        say("Saved.");
        await refresh();
      }
    } catch (e) { say(e.message); }
  });
  form.append(el("label", "small", kind === "move" ? "New place, like work/clients: " : "Note: "), input, save);
  input.focus();
}

/* ---------- the notes of a shelf ---------- */
const cardOptions = () => ({ selecting, picked, onPick: drawBulk, cancelEdit: () => drawNotes(true) });

async function drawNotes(reset) {
  if (trash) return drawTrash();
  const box = $("memlist"), more = $("memmore");
  if (reset) { box.replaceChildren(); offset = 0; }
  if (reset && selFile) {  // a note picked on the map is shown in full at the top
    try {
      const one = (await get(url("/api/memory", { ids: selFile }))).items[0];
      if (one) { const c = noteCard(one, cardOptions()); c.classList.add("picked"); box.append(c); }
    } catch (e) { /* the list below still works */ }
  }
  let items;
  try { items = (await get(url("/api/memory", { shelf: sel, q: query, offset, limit: PAGE }))).items; } catch (e) { say(e.message); return; }
  if (reset && !items.length) box.append(el("p", "empty", query ? "Nothing matches that search." : "Nothing on this shelf yet."));
  items.filter((r) => r.id !== selFile).forEach((r) => box.append(noteCard(r, cardOptions())));
  offset += items.length;
  more.hidden = items.length < PAGE;
}

function drawBulk() {
  const bar = $("bulkbar");
  bar.replaceChildren();
  bar.hidden = !selecting || trash;
  if (bar.hidden) return;
  const n = picked.size;
  bar.append(el("div", "small", n ? plural(n, "note") + " selected." : "Tick the notes you want to change."));
  if (!n) return;
  const run = async (body, done) => {
    try { await post("/api/memory", { action: "bulk", ids: [...picked], ...body }); picked.clear(); await refresh(); say("Saved: " + done); } catch (e) { say(e.message); }
  };
  const shelf = document.createElement("input");
  shelf.type = "text"; shelf.setAttribute("list", "shelfnames"); shelf.placeholder = "shelf, like work/clients"; shelf.maxLength = 200; shelf.setAttribute("aria-label", "Move them to this shelf");
  const acts = el("div", "acts");
  acts.append(shelf,
    btn("Move", "btn", () => run({ op: "move", shelf: shelf.value }, "moved " + plural(n, "note") + ".")),
    btn("Make secret", "btn", () => run({ op: "level", level: "high" }, plural(n, "note") + " now secret.")),
    btn("Make everyday", "btn", () => run({ op: "level", level: "low" }, plural(n, "note") + " now everyday.")),
    btn("Delete", "btn warn", (e) => confirmTwice(e.target, `Really delete ${n}?`, () => run({ op: "delete" }, plural(n, "note") + " moved to the trash."))));
  bar.append(acts);
}

async function drawTrash() {
  const box = $("memlist");
  box.replaceChildren();
  $("memmore").hidden = true;
  $("bulkbar").hidden = true;
  let items;
  try { items = (await get("/api/memory/trash")).items; } catch (e) { say(e.message); return; }
  const back = el("a", "linkbtn", "← Back to my notes");
  back.href = paths.shelf(sel);
  back.dataset.link = "";
  box.append(back);
  if (!items.length) { box.append(el("p", "empty", "The trash is empty. Deleted notes stay here for 30 days.")); return; }
  items.forEach((t) => {
    const c = el("div", "mem"), acts = el("div", "acts");
    acts.append(btn("Put it back", "btn go2", async () => {
      try { await post("/api/memory", { action: "restore", id: t.unit }); await refresh(); say("Saved: it is back."); } catch (e) { say(e.message); }
    }));
    c.append(el("div", "memtext", (t.long ? `📄 ${t.title}: ` : "") + t.preview),
      el("div", "small muted", `${t.shelf_name} · ${t.level === "low" ? "Everyday" : "Secret"} · gone for good in ${plural(t.days_left, "day")}`), acts);
    box.append(c);
  });
  box.append(btn("Empty the trash", "btn warn", (e) => confirmTwice(e.target, "Really empty it?", async () => {
    try { await post("/api/memory", { action: "empty_trash" }); drawTrash(); } catch (er) { say(er.message); }
  })));
}

/* ---------- putting the address and the screen together ---------- */
async function show() {
  if (sel && !shelves().some((s) => s.path === sel)) sel = "";
  map.reveal(sel);
  leaf = [];
  if (sel && !trash) {
    try { leaf = (await get(url("/api/memory", { shelf: sel, limit: 100 }))).items.filter((f) => f.shelf === sel); } catch (e) { leaf = []; }
  }
  drawStats();
  drawShelfActions();
  drawBulk();
  drawMap();
  drawProposals($("suggest"));
  await drawNotes(true);
  loadChats();
}

export const memoryView = {
  section: "view-memory",

  mount() {
    map = new MemoryMap($("memmap"), {
      shelf: (path) => navigate(paths.shelf(path)),
      file: (note) => navigate(paths.note(note.id)),
      chat: (id) => navigate(paths.chat(id))
    });
    map.pz.bindButtons($("mapzoomin"), $("mapzoomout"), $("mapfit"));
    window.addEventListener("resize", () => { if (!$("view-memory").hidden) map.pz.fit(); });
    $("mapexpand").onclick = () => map.expandAll();
    $("mapfold").onclick = () => map.foldAll();
    $("selectmode").onclick = () => { selecting = !selecting; picked.clear(); $("selectmode").textContent = selecting ? "Done selecting" : "Select several"; drawBulk(); drawNotes(true); };
    $("memq").oninput = debounce(() => { query = $("memq").value.trim(); drawNotes(true); }, 300);
    $("memmore").onclick = () => drawNotes(false);
    $("addbtn").onclick = () => openAdd({ shelf: sel });
    setupMemoryForms();
  },

  async enter(params) {
    trash = params.mode === "trash";
    selFile = null;
    if (params.mode === "note") {
      try {
        const note = (await get(url("/api/memory", { ids: params.id }))).items[0];
        if (!note) throw new Error("That note is no longer in your memory.");
        sel = note.shelf; selFile = note.id;
      } catch (e) { toast(e.message, true); navigate(paths.memory(), { replace: true }); return; }
    } else if (params.mode === "shelf") sel = params.path;
    else if (params.mode === "all") sel = "";
    map.fitNext = map.fitNext || params.mode === "all";
    await show();
  },

  leave() {},

  /** The shared state changed (a note was saved, moved, deleted): draw again, keeping where we are. */
  redraw() {
    if ($("view-memory").hidden) return;
    show();
  }
};
