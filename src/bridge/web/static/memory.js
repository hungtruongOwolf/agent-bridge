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
  function drawTree() {
    const box = $("shelftree"); box.replaceChildren();
    const m = B.state().memory, all = btn("Everything (" + m.total + ")", "shelfrow" + (sel === "" ? " on" : ""), () => select(""));
    box.append(all);
    if (!m.total) { box.append(el("p", "empty", "Your memory is empty. Add something on the right, or say yes to a helper's suggestion.")); return; }
    const ul = el("ul", "shelves");
    shelves().filter(visible).forEach((s) => {
      const li = el("li"); li.style.paddingLeft = (s.depth * 16) + "px";
      const tg = s.has_children ? btn(expanded.has(s.path) ? "▾" : "▸", "twist", () => { expanded.has(s.path) ? expanded.delete(s.path) : expanded.add(s.path); drawTree(); }) : el("span", "twist");
      if (s.has_children) tg.setAttribute("aria-label", (expanded.has(s.path) ? "Fold " : "Unfold ") + s.name);
      const row = btn("", "shelfrow" + (sel === s.path ? " on" : ""), () => select(s.path));
      row.append(el("span", "sn", s.name), el("span", "cnt", String(s.count)));
      if (s.secret) row.append(el("span", "tag wait", s.secret + " secret"));
      li.append(tg, row);
      if (s.label) li.append(el("div", "small muted shelfnote", s.label));
      else if (s.keywords.length) li.append(el("div", "small muted shelfnote", s.keywords.slice(0, 4).join(", ")));
      ul.append(li);
    });
    box.append(ul);
    const dl = $("shelfnames"); dl.replaceChildren();
    shelves().forEach((s) => { const o = document.createElement("option"); o.value = s.path; dl.append(o); });
  }

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
    drawTree(); drawShelfActions();
    if (!$("view-memory").hidden) drawFiles(true);
    const np = $("notespanel"); if (np) { const n = proposals($("notes")); np.hidden = !n; }
  }
  function show() { redraw(); }
  function mount(bridge) { B = bridge; setupForm(); setupImport(); redraw(); }
  window.MemoryUI = { mount, redraw, show, proposals, pretty };
})();
