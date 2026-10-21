/* One note as a card: its text (a long note shows a preview and can be read whole), where it came from, where it was used,
   and Edit / Delete (to the trash, with an undo) / earlier versions. */
import { el, btn, confirmTwice } from "../lib/dom.js";
import { get, post, url } from "../lib/api.js";
import { refresh } from "../lib/store.js";
import { toast, say } from "../lib/toast.js";
import { plural, when } from "../lib/format.js";

const PREVIEW = 420;

export function levelSelect(value) {
  const s = document.createElement("select");
  s.setAttribute("aria-label", "Everyday or secret");
  [["low", "Everyday: helpers can be given this"], ["high", "Secret: never leaves this page"]].forEach(([k, t]) => {
    const o = document.createElement("option");
    o.value = k; o.textContent = t;
    s.append(o);
  });
  s.value = value === "low" ? "low" : "high";
  return s;
}

function longBody(r) {
  const wrap = document.createDocumentFragment(), body = el("div", "memtext", r.text.length > PREVIEW ? r.text.slice(0, PREVIEW).trimEnd() + "…" : r.text);
  wrap.append(el("div", "notetitle", "📄 " + r.title), body);
  if (r.text.length > PREVIEW) {
    const label = `Read the whole note (${r.chars.toLocaleString()} characters)`;
    const more = btn(label, "linkbtn", () => {
      const open = more.dataset.open === "1";
      more.dataset.open = open ? "0" : "1";
      body.textContent = open ? r.text.slice(0, PREVIEW).trimEnd() + "…" : r.text;
      body.classList.toggle("fulltext", !open);
      more.textContent = open ? label : "Show less";
    });
    wrap.append(more);
  }
  return wrap;
}

async function versions(card, r) {
  let box = card.querySelector(".versions");
  if (box) { box.remove(); return; }
  box = el("div", "versions");
  card.append(box);
  try {
    const list = (await get(url("/api/memory/history", { id: r.id }))).versions;
    if (!list.length) { box.append(el("p", "small muted", "No earlier versions were kept.")); return; }
    list.forEach((v) => {
      const row = el("div", "vrow");
      row.append(el("div", "small muted", when(v.at) + " · " + v.chars.toLocaleString() + " characters"), el("div", "small vtext", v.text.length > 220 ? v.text.slice(0, 220) + "…" : v.text));
      row.append(btn("Put this version back", "linkbtn", async () => {
        try { await post("/api/memory", { action: "restore_version", id: r.id, index: v.index }); await refresh(); say("Saved: the earlier version is back."); } catch (e) { say(e.message); }
      }));
      box.append(row);
    });
  } catch (e) { box.append(el("p", "small warnline", e.message)); }
}

function edit(card, r, cancel) {
  card.replaceChildren();
  const text = document.createElement("textarea"), title = document.createElement("input"), shelf = document.createElement("input"), level = levelSelect(r.sensitivity);
  text.value = r.text; text.rows = r.long ? 14 : 4; text.maxLength = 80000; text.setAttribute("aria-label", "Text of this note");
  title.type = "text"; title.maxLength = 120; title.value = r.title || ""; title.setAttribute("aria-label", "Title of this long note");
  shelf.type = "text"; shelf.value = r.shelf; shelf.setAttribute("aria-label", "Shelf"); shelf.setAttribute("list", "shelfnames");
  const acts = el("div", "acts");
  acts.append(btn("Save", "btn go2", async () => {
    try {
      await post("/api/memory", { action: "update", id: r.id, text: text.value, sensitivity: level.value, shelf: shelf.value, ...(r.long ? { title: title.value } : {}) });
      await refresh();
    } catch (e) { say(e.message); }
  }), btn("Cancel", "btn", cancel));
  card.append(text);
  if (r.long) card.append(el("label", "small fieldrow", "Title "), title);
  card.append(el("label", "small fieldrow", "Shelf "), shelf, level, acts);
}

/**
 * r: a note from /api/memory.
 * opts: { selecting, picked (Set), onPick(), cancelEdit() } — selection mode adds a tick box, and cancelling an edit redraws the list.
 */
export function noteCard(r, opts) {
  const c = el("div", "mem" + (r.long ? " longnote" : "") + (opts.picked.has(r.id) ? " chosen" : ""));
  if (opts.selecting) {
    const l = el("label", "pickrow small"), cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = opts.picked.has(r.id); cb.setAttribute("aria-label", "Select this note");
    cb.onchange = () => { cb.checked ? opts.picked.add(r.id) : opts.picked.delete(r.id); c.classList.toggle("chosen", cb.checked); opts.onPick(); };
    l.append(cb, " Select");
    c.append(l);
  }
  c.append(r.long ? longBody(r) : el("div", "memtext", r.text));

  const meta = el("div", "small muted");
  meta.append((r.source === "helper" ? `Suggested by ${r.helper}, saved because you said yes` : "Written by you") + (r.created ? " on " + when(r.created) : "") + ". ");
  meta.append(el("span", "tag " + (r.sensitivity === "low" ? "good" : "wait"), r.sensitivity === "low" ? "Everyday" : "Secret"), " ", r.shelf_name + ".");
  if (r.long) meta.append(` Kept whole, stored as ${r.parts} passages so a helper reads only the part it needs.`);
  if (r.edited) { meta.append(" You corrected it later. "); meta.append(btn("See earlier versions", "linkbtn", () => versions(c, r))); }
  c.append(meta, el("div", "small muted", r.used.answers ? `Helped write ${plural(r.used.answers, "answer")}; last in “${r.used.last_chat}”.` : "Not used in any answer yet."));

  const acts = el("div", "acts");
  acts.append(btn("Edit", "btn", () => edit(c, r, opts.cancelEdit)), btn("Delete", "btn warn", (e) => confirmTwice(e.target, "Really delete?", async () => {
    try {
      await post("/api/memory", { action: "delete", id: r.id });
      await refresh();
      toast("Moved to the trash. It stays there for 30 days.", false, { label: "Undo", fn: async () => {
        try { await post("/api/memory", { action: "restore", id: r.id }); await refresh(); say("Saved: it is back."); } catch (er) { say(er.message); }
      } });
    } catch (er) { say(er.message); }
  })));
  if (r.source === "helper" && r.from_run) {  // a helper's suggestion can be taken back together with everything else that answer added
    acts.append(btn("Undo what that answer added", "btn", async () => {
      try {
        const out = await post("/api/revert", { run_id: r.from_run });
        await refresh();
        say(`Undone: ${plural(out.removed_from_vault, "note")} removed` + (out.kept_because_edited ? `, ${out.kept_because_edited} kept because you changed ${out.kept_because_edited === 1 ? "it" : "them"}.` : "."));
      } catch (er) { say(er.message); }
    }));
  }
  c.append(acts);
  return c;
}
