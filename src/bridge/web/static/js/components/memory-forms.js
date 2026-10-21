/* Putting things into memory: write or paste a note, bring in a text file (as one long note or split into short ones),
   and the backup download and restore. */
import { $, el, btn } from "../lib/dom.js";
import { get, post } from "../lib/api.js";
import { refresh } from "../lib/store.js";
import { say } from "../lib/toast.js";
import { plural } from "../lib/format.js";
import { levelSelect } from "./note-card.js";

const MAX_NOTE = 80000, MAX_FILE = 300000, MAX_BACKUP = 380000, LONG_FROM = 1500;

function countChars() {
  const n = $("memtext").value.length, long = n > LONG_FROM;
  $("memcount").textContent = n ? n.toLocaleString() + " of 80,000 characters" + (long ? ". This is a long note: it is kept whole and cut into passages for helpers." : "") : "";
  $("memtitlerow").hidden = !long;
}

/** Cut a text file into short notes at blank lines; a long paragraph is cut at a sentence end. */
export function splitNotes(text) {
  const out = [];
  text.replace(/\r\n/g, "\n").split(/\n\s*\n/).forEach((para) => {
    let p = para.trim().replace(/[ \t]+/g, " ");
    if (!p) return;
    while (p.length > 800) {
      let cut = p.lastIndexOf(". ", 800);
      if (cut < 200) cut = p.lastIndexOf(" ", 800);
      if (cut < 200) cut = 800;
      out.push(p.slice(0, cut + 1).trim());
      p = p.slice(cut + 1).trim();
    }
    if (p) out.push(p);
  });
  return out;
}

function setupAdd() {
  const level = levelSelect("low");
  $("memlevelslot").replaceChildren(level);
  $("memform").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const r = await post("/api/memory", { action: "add", type: $("memkind").value, text: $("memtext").value, sensitivity: level.value, shelf: $("memshelf").value, title: $("memtitle").value });
      $("memtext").value = ""; $("memtitle").value = "";
      countChars();
      say(r.similar && r.similar.length ? `Saved. You already have a very similar note: “${r.similar[0].text.slice(0, 80)}” (${r.similar[0].shelf_name}).` : r.id.startsWith("doc") ? "Saved as one long note." : "Saved.");
      await refresh();
    } catch (er) { say(er.message); }
  };
  $("memtext").oninput = countChars;
  countChars();
}

function importChoices(box, raw, base) {
  const level = levelSelect("low"), shelf = document.createElement("input");
  shelf.type = "text"; shelf.setAttribute("list", "shelfnames"); shelf.maxLength = 200; shelf.setAttribute("aria-label", "Shelf for these notes");
  shelf.value = base.toLowerCase().replace(/[^\p{L}\p{N} -]+/gu, " ").trim().slice(0, 30);
  const canWhole = raw.length <= MAX_NOTE, mode = { v: canWhole ? "whole" : "split" }, notes = splitNotes(raw).slice(0, 50), ticks = [];
  const pick = el("div", "modepick"), listBox = el("div");
  const drawList = () => {
    listBox.replaceChildren();
    ticks.length = 0;
    if (mode.v === "whole") { listBox.append(el("p", "small muted", "It will be saved whole and cut into passages behind the scenes.")); return; }
    listBox.append(el("p", "small", `Found ${plural(notes.length, "note")}. Untick the ones you do not want.`));
    const list = el("ul", "filelist");
    notes.forEach((t) => {
      const li = el("li"), c = document.createElement("input");
      c.type = "checkbox"; c.checked = true; c.setAttribute("aria-label", "Keep: " + t.slice(0, 60));
      ticks.push(c);
      li.append(c, el("span", null, t));
      list.append(li);
    });
    listBox.append(list);
  };
  [["whole", `Keep it as one long note (${raw.length.toLocaleString()} characters)`], ["split", "Split it into short notes"]].forEach(([v, t]) => {
    const l = el("label", "small"), r = document.createElement("input");
    r.type = "radio"; r.name = "impmode"; r.value = v; r.checked = mode.v === v; r.disabled = v === "whole" && !canWhole;
    r.onchange = () => { mode.v = v; drawList(); };
    l.append(r, " " + t);
    pick.append(l);
  });
  drawList();
  const row = el("div", "composerrow");
  row.append(el("label", "small", "Put it on shelf "), shelf, level);
  const save = btn("Save", "btn go2", async () => {
    const items = mode.v === "whole" ? [{ title: base, text: raw }] : notes.filter((_, i) => ticks[i].checked);
    if (!items.length) { say("Tick at least one note."); return; }
    save.disabled = true;
    try {
      await post("/api/memory", { action: "add_many", items, sensitivity: level.value, type: "note", shelf: shelf.value });
      box.replaceChildren(); $("memfile").value = "";
      say("Saved.");
      await refresh();
    } catch (e) { say(e.message); save.disabled = false; }
  });
  box.append(pick, listBox, row, save);
}

function setupImport() {
  $("memfile").onchange = async (ev) => {
    const f = ev.target.files[0], box = $("importbox");
    box.replaceChildren();
    if (!f) return;
    if (f.size > MAX_FILE) { box.append(el("p", "warnline", "That file is bigger than 300 KB. Cut it into smaller parts first.")); return; }
    const raw = (await f.text()).replace(/\r\n/g, "\n").trim();
    if (!raw) { box.append(el("p", "warnline", "There is no text in that file.")); return; }
    importChoices(box, raw, f.name.replace(/\.[^.]+$/, ""));
  };
}

function setupBackup() {
  $("memexport").onclick = async () => {
    try {
      const data = await get("/api/memory/export"), blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "my-memory-backup.json";
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      say(`Saved: a backup with ${plural(data.notes, "note")} was downloaded.`);
    } catch (e) { say(e.message); }
  };
  $("memrestore").onchange = async (ev) => {
    const f = ev.target.files[0];
    if (!f) return;
    if (f.size > MAX_BACKUP) { say("That file is too big to put back here (the limit is 380 KB)."); return; }
    try {
      const out = await post("/api/memory", { action: "restore_backup", backup: JSON.parse(await f.text()) });
      say(`Saved: ${plural(out.added, "note")} put back` + (out.skipped ? `, ${out.skipped} already here were left alone.` : "."));
      await refresh();
    } catch (e) { say(e instanceof SyntaxError ? "That file is not a backup." : e.message); }
    ev.target.value = "";
  };
}

export function setupMemoryForms() {
  setupAdd();
  setupImport();
  setupBackup();
}
