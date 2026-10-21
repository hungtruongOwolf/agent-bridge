/* Adding to memory, in one place: a dialog you can open from anywhere on the memory screen.
   1. what to save (write one note, paste several, or bring in a text file),
   2. where it goes (pick a shelf from the tree, or make a new one right there, several levels at once if you like),
   3. who may see it (everyday or secret).
   The shelf you were looking at is already chosen, so adding "here" takes one click and some typing. */
import { $, el, btn } from "../lib/dom.js";
import { post } from "../lib/api.js";
import { getState, refresh } from "../lib/store.js";
import { navigate, paths } from "../lib/nav.js";
import { plural, pretty } from "../lib/format.js";
import { say } from "../lib/toast.js";
import { pastedNotes, splitNotes } from "../lib/notes.js";

const MAX_NOTE = 80000, MAX_FILE = 300000, LONG_FROM = 1500, MAX_MANY = 50, DEFAULT_SHELF = "inbox";
const MODES = [["write", "Write a note"], ["many", "Paste several"], ["file", "From a file"]];

const tidy = (raw) => raw.split(/[\\/]/).map((p) => p.trim().toLowerCase().replace(/\s+/g, " ")).filter(Boolean).join("/");

/* ---------- the shelf chooser ---------- */
function chooser(start) {
  const shelves = getState().memory.shelves, byParent = {};
  shelves.forEach((s) => { (byParent[s.parent] = byParent[s.parent] || []).push(s); });
  const st = { path: start || "", open: new Set(), listOpen: false };
  const up = (p) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
  for (let p = up(st.path); p; p = up(p)) st.open.add(p);

  const root = el("div", "chooser"), where = el("div", "where"), list = el("div", "treelist"), fresh = document.createElement("input"), preview = el("div", "small");
  fresh.type = "text"; fresh.maxLength = 300; fresh.placeholder = "A new shelf inside it, like Q4 pricing, or Q4/pricing/discounts"; fresh.setAttribute("aria-label", "Name of a new shelf");

  const finalPath = () => {
    const extra = tidy(fresh.value);
    return [st.path, extra].filter(Boolean).join("/") || DEFAULT_SHELF;
  };
  const known = (p) => p === DEFAULT_SHELF || shelves.some((s) => s.path === p);

  const drawWhere = () => {
    const p = finalPath(), parts = p.split("/"), have = [];
    let acc = "";
    parts.forEach((seg) => { acc = acc ? acc + "/" + seg : seg; have.push(known(acc) || (acc === DEFAULT_SHELF)); });
    where.replaceChildren(el("span", "small muted", "Goes on: "));
    parts.forEach((seg, i) => {
      if (i) where.append(el("span", "sep", " › "));
      where.append(el("b", have[i] ? "seg" : "seg isnew", seg.replace(/\b\p{L}/gu, (c) => c.toUpperCase())));
    });
    preview.textContent = have.every(Boolean) ? "" : "Shelves in orange do not exist yet: they are made when you save.";
  };

  const drawList = () => {
    list.hidden = !st.listOpen;
    list.replaceChildren();
    if (!st.listOpen) return;
    const row = (label, path, depth, has) => {
      const r = el("div", "trow" + (st.path === path ? " on" : ""));
      r.style.paddingLeft = 6 + Math.min(depth, 8) * 14 + "px";
      const tw = el("button", "twist", has ? (st.open.has(path) ? "▾" : "▸") : "");
      tw.type = "button"; tw.disabled = !has; tw.setAttribute("aria-label", "Open or close " + label);
      tw.onclick = () => { st.open.has(path) ? st.open.delete(path) : st.open.add(path); drawList(); };
      const pick = el("button", "pickshelf", label);
      pick.type = "button";
      pick.onclick = () => { st.path = path; if (has) st.open.add(path); drawList(); drawWhere(); };
      r.append(tw, pick);
      list.append(r);
    };
    row("Top level (no shelf above it)", "", 0, false);
    const walk = (parent, depth) => (byParent[parent] || []).forEach((s) => {
      row(s.name + " (" + s.count + ")", s.path, depth, !!(byParent[s.path] || []).length);
      if (st.open.has(s.path)) walk(s.path, depth + 1);
    });
    walk("", 1);
  };

  const toggle = btn("Choose a shelf", "btn sm", () => { st.listOpen = !st.listOpen; toggle.textContent = st.listOpen ? "Done choosing" : "Choose a shelf"; drawList(); });
  toggle.type = "button";
  fresh.oninput = drawWhere;
  root.append(where, toggle, list, fresh, preview);
  drawWhere();
  drawList();
  return { el: root, path: finalPath, focusNew: () => { st.listOpen = false; drawList(); fresh.focus(); } };
}

/* ---------- the three ways to give it text ---------- */
function writePane() {
  const box = el("div", "pane"), text = document.createElement("textarea"), count = el("div", "small muted"), titleRow = el("label", "small fieldrow", "Title "), title = document.createElement("input");
  text.rows = 7; text.maxLength = MAX_NOTE; text.placeholder = "Write or paste anything: a short fact, or a whole page of notes. Long notes are kept whole."; text.setAttribute("aria-label", "What to remember");
  title.type = "text"; title.maxLength = 120; title.placeholder = "optional"; title.setAttribute("aria-label", "Title of this long note");
  titleRow.append(title); titleRow.hidden = true;
  text.oninput = () => {
    const n = text.value.length, long = n > LONG_FROM;
    count.textContent = n ? n.toLocaleString() + " of 80,000 characters" + (long ? ". A long note is kept whole and cut into passages for helpers." : "") : "";
    titleRow.hidden = !long;
  };
  box.append(text, count, titleRow);
  return { el: box, focus: () => text.focus(), ready: () => text.value.trim().length > 0, clear: () => { text.value = ""; title.value = ""; text.oninput(); text.focus(); },
           body: () => ({ text: text.value, title: title.value }), many: () => null };
}

function manyPane() {
  const box = el("div", "pane"), text = document.createElement("textarea"), info = el("div", "small muted");
  text.rows = 8; text.setAttribute("aria-label", "Several notes, one per line");
  text.placeholder = "One note per line:\nAcme prefers email on Mondays\nHooli renews in March\n\n(or separate longer notes with a blank line)";
  text.oninput = () => {
    const n = pastedNotes(text.value).length;
    info.textContent = !n ? "" : n > MAX_MANY ? `${n} notes found. Up to ${MAX_MANY} are saved at a time.` : plural(n, "note") + " found.";
  };
  box.append(text, info);
  return { el: box, focus: () => text.focus(), ready: () => pastedNotes(text.value).length > 0, clear: () => { text.value = ""; text.oninput(); text.focus(); },
           body: () => null, many: () => pastedNotes(text.value).slice(0, MAX_MANY) };
}

function filePane() {
  const box = el("div", "pane"), input = document.createElement("input"), area = el("div"), state = { items: null, name: "" };
  input.type = "file"; input.accept = ".txt,.md,.csv,text/plain"; input.setAttribute("aria-label", "Choose a text file to import");
  box.append(el("p", "small muted", "A .txt, .md or .csv file, up to 300 KB. Keep it as one long note, or split it into short notes."), input, area);
  input.onchange = async () => {
    area.replaceChildren(); state.items = null;
    const f = input.files[0];
    if (!f) return;
    if (f.size > MAX_FILE) { area.append(el("p", "warnline", "That file is bigger than 300 KB. Cut it into smaller parts first.")); return; }
    const raw = (await f.text()).replace(/\r\n/g, "\n").trim();
    if (!raw) { area.append(el("p", "warnline", "There is no text in that file.")); return; }
    const base = f.name.replace(/\.[^.]+$/, ""), canWhole = raw.length <= MAX_NOTE, notes = splitNotes(raw).slice(0, MAX_MANY), ticks = [];
    const mode = { v: canWhole ? "whole" : "split" }, pick = el("div", "modepick"), listBox = el("div");
    const commit = () => { state.items = mode.v === "whole" ? [{ title: base, text: raw }] : notes.filter((_, i) => ticks[i] && ticks[i].checked); };
    const drawList = () => {
      listBox.replaceChildren(); ticks.length = 0;
      if (mode.v === "whole") { listBox.append(el("p", "small muted", "It will be saved whole and cut into passages behind the scenes.")); commit(); return; }
      listBox.append(el("p", "small", `Found ${plural(notes.length, "note")}. Untick the ones you do not want.`));
      const ul = el("ul", "filelist");
      notes.forEach((t) => {
        const li = el("li"), c = document.createElement("input");
        c.type = "checkbox"; c.checked = true; c.onchange = commit; c.setAttribute("aria-label", "Keep: " + t.slice(0, 60));
        ticks.push(c);
        li.append(c, el("span", null, t));
        ul.append(li);
      });
      listBox.append(ul);
      commit();
    };
    [["whole", `Keep it as one long note (${raw.length.toLocaleString()} characters)`], ["split", "Split it into short notes"]].forEach(([v, t]) => {
      const l = el("label", "small"), r = document.createElement("input");
      r.type = "radio"; r.name = "impmode"; r.checked = mode.v === v; r.disabled = v === "whole" && !canWhole;
      r.onchange = () => { mode.v = v; drawList(); };
      l.append(r, " " + t);
      pick.append(l);
    });
    area.append(pick, listBox);
    drawList();
  };
  return { el: box, focus: () => input.focus(), ready: () => !!(state.items && state.items.length), clear: () => { input.value = ""; area.replaceChildren(); state.items = null; },
           body: () => null, many: () => state.items };
}

/* ---------- the dialog ---------- */
/** opts: { shelf: the shelf to start on, newShelf: put the cursor in the "new shelf" box, mode: "write" | "many" | "file" } */
export function openAdd(opts = {}) {
  const dlg = $("adddlg"), body = $("adddlgbody");
  const panes = { write: writePane(), many: manyPane(), file: filePane() };
  let mode = MODES.some(([k]) => k === opts.mode) ? opts.mode : "write";
  const where = chooser(opts.shelf || "");

  const tabs = el("div", "ptabs", ""), slot = el("div"), level = { v: "low" }, person = document.createElement("input"), status = el("p", "small warnline");
  tabs.setAttribute("role", "tablist");
  const drawMode = () => {
    [...tabs.children].forEach((b) => b.setAttribute("aria-selected", String(b.dataset.mode === mode)));
    slot.replaceChildren(panes[mode].el);
    person.closest("label").hidden = mode !== "write";
    status.textContent = "";
    panes[mode].focus();
  };
  MODES.forEach(([k, t]) => {
    const b = btn(t, "", () => { mode = k; drawMode(); });
    b.type = "button"; b.dataset.mode = k; b.setAttribute("role", "tab");
    tabs.append(b);
  });

  const cards = el("div", "levelcards");
  [["low", "Everyday", "Helpers can be given this when you tick its shelf."], ["high", "Secret", "Never leaves this page, even if its shelf is ticked."]].forEach(([k, t, d]) => {
    const l = el("label", "levelcard"), r = document.createElement("input");
    r.type = "radio"; r.name = "addlevel"; r.checked = k === "low";
    r.onchange = () => { level.v = k; };
    const text = el("span"); text.append(el("b", null, t), el("span", "small muted", d));
    l.append(r, text);
    cards.append(l);
  });
  person.type = "checkbox";
  const personRow = el("label", "small"); personRow.append(person, " This note is about a person");

  const save = async (again) => {
    const pane = panes[mode], path = where.path();
    if (!pane.ready()) { status.textContent = mode === "file" ? "Choose a file first." : "Write something first."; pane.focus(); return; }
    saveBtn.disabled = anotherBtn.disabled = true;
    try {
      let r, n = 1;
      if (mode === "write") {
        const b = pane.body();
        r = await post("/api/memory", { action: "add", type: person.checked ? "contact" : "note", text: b.text, sensitivity: level.v, shelf: path, title: b.title });
      } else {
        const items = pane.many();
        n = items.length;
        r = await post("/api/memory", { action: "add_many", items, sensitivity: level.v, type: "note", shelf: path });
      }
      const dup = r && r.similar && r.similar.length ? ` You already have a very similar note: “${r.similar[0].text.slice(0, 70)}”.` : "";
      say(`Saved ${n > 1 ? plural(n, "note") : "it"} on ${pretty(path)}.` + dup);
      await refresh();
      if (again) { pane.clear(); }
      else { dlg.close(); navigate(paths.shelf(path)); }
    } catch (e) { status.textContent = e.message; }
    saveBtn.disabled = anotherBtn.disabled = false;
  };
  const saveBtn = btn("Save", "btn go2", () => save(false)), anotherBtn = btn("Save and add another", "btn", () => save(true)), cancel = btn("Cancel", "btn", () => dlg.close());
  [saveBtn, anotherBtn, cancel].forEach((b) => { b.type = "button"; });

  body.replaceChildren(
    el("h2", null, "Add to memory"), tabs, slot,
    el("h3", "sub", "Where should it go?"), where.el,
    el("h3", "sub", "Who may see it?"), cards, personRow, status,
    Object.assign(el("div", "acts"), {}),
  );
  body.lastChild.append(saveBtn, anotherBtn, cancel);
  body.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(false); } };
  drawMode();
  if (!dlg.open) dlg.showModal();
  if (opts.newShelf) where.focusNew(); else panes[mode].focus();
}
