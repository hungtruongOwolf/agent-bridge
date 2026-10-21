/* The small office of one chat: a safe with the top shelves as drawers, a glass room where the helper works, a guard.
   After each answer it replays what really happened, from the run's own journal. */
import { Office } from "../pixel/office.js";
import "../pixel/story.js";  // adds Office.prototype.play and friends
import { get, url } from "../lib/api.js";

const topShelf = (p) => (p && p.includes("/") ? p.slice(0, p.indexOf("/")) : p);

export class MiniOffice {
  /** canvas, caption and title are elements; onDrawer(path) is called when a drawer is clicked. */
  constructor({ canvas, caption, title, onDrawer }) {
    this.canvas = canvas;
    this.captionEl = caption;
    this.titleEl = title;
    this.onDrawer = onDrawer;
    this.office = null;
  }

  /** The canvas is measured when the office is created, so create it only once the chat screen is visible. */
  ensure() {
    if (this.office) return this.office;
    this.office = new Office(this.canvas, { onDrawer: (path) => this.onDrawer(path) });
    this.office.pace = 1.6;
    return this.office;
  }

  caption(text) {
    this.captionEl.textContent = text;
    this.canvas.setAttribute("aria-label", text);
  }

  /** Show the helper of this chat, idle, with the right drawers. */
  show(agent, shelves) {
    const o = this.ensure();
    o.showIdle(agent && agent.available ? { id: agent.id, name: agent.name, status: agent.status } : null);
    this.setDrawers(shelves);
    this.titleEl.textContent = agent && agent.available ? agent.name + "'s office" : "This chat's office";
  }

  setDrawers(shelves) {
    if (!this.office) return;
    const top = (shelves || []).filter((s) => s.depth === 0).slice(0, 4);
    this.office.setDrawers(top.map((s) => ({ type: s.path, label: s.name, count: s.count, open: s.state !== "closed", locked: s.secret > 0 })));
  }

  working(agent, shelves) {
    this.show(agent, shelves);
    this.office.say("agent", "Let me see…", 3000);
    this.caption("The helper is working on your message.");
  }

  resize() {
    if (this.office) window.dispatchEvent(new Event("resize"));
  }

  /** Act out a finished run. `stillHere()` says whether this chat is still the one on screen. */
  async replay(report, stillHere) {
    if (!this.office || !report || !report.journal) return;
    const recs = new Map();
    try {
      const ids = (report.records_handed || []).slice(0, 50);
      if (ids.length) {
        (await get(url("/api/memory", { limit: 100, ids: ids.join(",") }))).items.forEach((r) => recs.set(r.id, { type: topShelf(r.shelf), sensitivity: r.sensitivity }));
      }
    } catch (e) { /* the picture still plays without file positions */ }
    try {
      await this.office.play(report, { animate: true, records: recs, log: () => {}, caption: (t) => { if (stillHere()) this.caption(t); } });
    } catch (e) { /* the answer is already on screen */ }
  }
}
