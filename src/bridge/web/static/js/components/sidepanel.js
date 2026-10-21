/* "What the helper sees": the memory tree with tick boxes, a one-line summary, and the less common settings folded away. */
import { el, btn, confirmTwice } from "../lib/dom.js";
import { plural } from "../lib/format.js";

export class SidePanel {
  /**
   * box: the element to draw in.
   * actions: { settings(patch), clear(), remove() } — all asynchronous changes go through the chat view.
   */
  constructor(box, actions) {
    this.box = box;
    this.actions = actions;
    this.open = new Set();  // folded-out shelves
    this.moreOpen = false;
  }

  #visible(s) {
    for (let p = s.parent; p; p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "") if (!this.open.has(p)) return false;
    return true;
  }

  async toggleShelf(chat, ctx, path) {
    const s = ctx.shelves.find((x) => x.path === path);
    if (!s) return;
    if (chat.lens.shelves.includes(path)) return this.actions.settings({ shelves: chat.lens.shelves.filter((p) => p !== path) });
    if (s.state === "open") return;  // open because a shelf above it is open
    return this.openShelf(chat, path);
  }

  openShelf(chat, path) {
    const shelves = [...chat.lens.shelves.filter((p) => !p.startsWith(path + "/")), path].filter((p, i, a) => a.indexOf(p) === i);
    return this.actions.settings({ shelves });
  }

  render(chat, ctx) {
    const box = this.box;
    box.replaceChildren(el("p", "small", "Tick the shelves this helper may look at."));
    box.append(this.#tree(chat, ctx));
    box.append(el("p", "seesum", ctx.shared_count ? "It can see " + plural(ctx.shared_count, "file") + "." : "It can see nothing yet, so it answers from your message alone."));
    if (ctx.walk && ctx.walk.length) box.append(el("p", "small walk", "For your message it would look in: " + ctx.walk.join(", ") + "."));
    if (ctx.secret) box.append(el("p", "small muted", "🔒 " + (ctx.secret === 1 ? "1 secret file is" : ctx.secret + " secret files are") + " never shared."));
    box.append(this.#more(chat, ctx));
  }

  #tree(chat, ctx) {
    const tree = el("ul", "shelves sidetree");
    if (!ctx.shelves.length) tree.append(el("li", "empty", "Your memory is empty. Add notes in My memory."));
    const inherited = (s) => s.state === "open" && !chat.lens.shelves.includes(s.path);
    ctx.shelves.filter((s) => this.#visible(s)).forEach((s) => {
      const li = el("li");
      li.style.paddingLeft = s.depth * 14 + "px";
      const twist = s.has_children
        ? btn(this.open.has(s.path) ? "▾" : "▸", "twist", () => { this.open.has(s.path) ? this.open.delete(s.path) : this.open.add(s.path); this.render(chat, ctx); })
        : el("span", "twist");
      const lab = el("label", "shelfpick" + (s.state === "open" ? " on" : s.state === "partly" ? " part" : "")), c = document.createElement("input");
      c.type = "checkbox";
      c.checked = s.state === "open";
      c.indeterminate = s.state === "partly";
      c.disabled = inherited(s);
      c.setAttribute("aria-label", "Let the helper see " + s.name + (inherited(s) ? " (open because a shelf above it is open)" : ""));
      c.onchange = () => this.toggleShelf(chat, ctx, s.path);
      lab.append(c, el("span", "sn", s.name), el("span", "cnt", String(s.count)));
      if (s.secret) lab.append(el("span", "tag wait", s.secret + " secret"));
      li.append(twist, lab);
      tree.append(li);
    });
    return tree;
  }

  #more(chat, ctx) {
    const more = el("details", "more");
    more.open = this.moreOpen;
    more.addEventListener("toggle", () => { this.moreOpen = more.open; });
    more.append(el("summary", null, "More settings"), el("h3", "sub", "Every file it can see (" + ctx.shared_count + ")"));

    const ul = el("ul", "filelist");
    ctx.shared.forEach((f) => {
      const li = el("li"), c = document.createElement("input");
      c.type = "checkbox";
      c.checked = true;
      c.setAttribute("aria-label", "Share: " + f.text);
      c.onchange = () => this.actions.settings({ exclude: [...chat.lens.exclude, f.id], include: chat.lens.include.filter((x) => x !== f.id) });
      li.append(c, el("span", null, f.text));
      if (ctx.likely.includes(f.id)) li.append(el("span", "tag good", "matches your message"));
      ul.append(li);
    });
    if (!ctx.shared.length) ul.append(el("li", "empty", "Nothing. The helper will answer from your message alone."));
    if (ctx.shared_more) ul.append(el("li", "empty", "…and " + ctx.shared_more + " more."));
    more.append(ul);

    if (ctx.held_back.length) {
      more.append(el("h3", "sub", "You held these back (" + ctx.held_back.length + ")"));
      const lk = el("ul", "filelist locked");
      ctx.held_back.forEach((f) => {
        const li = el("li"), c = document.createElement("input");
        c.type = "checkbox";
        c.checked = false;
        c.setAttribute("aria-label", "Share again: " + f.text);
        c.onchange = () => this.actions.settings({ exclude: chat.lens.exclude.filter((x) => x !== f.id) });
        li.append(c, el("span", null, f.shelf_name + ": " + f.text));
        lk.append(li);
      });
      more.append(lk);
    }

    const num = document.createElement("input");
    num.type = "number"; num.min = 0; num.max = 10; num.value = chat.history_turns;
    num.setAttribute("aria-label", "How many earlier messages the helper is shown");
    num.onchange = () => this.actions.settings({ history_turns: parseInt(num.value, 10) });
    const h = el("div", "setrow");
    h.append(el("label", "small", "The helper remembers the last "), num, el("span", "small", " messages of this chat."));
    more.append(h, el("p", "small muted", ctx.history.length ? "Right now it would see " + plural(ctx.history.length, "earlier message") + "." : "Right now it would see no earlier messages."));

    const lim = document.createElement("input");
    lim.type = "number"; lim.min = 0; lim.max = 10000; lim.step = 10; lim.value = chat.budget.limit;
    lim.setAttribute("aria-label", "Spending limit in cents");
    lim.onchange = () => this.actions.settings({ budget_cents: parseInt(lim.value, 10) });
    const bd = el("div", "setrow");
    bd.append(el("label", "small", "Most this chat may spend (cents) "), lim);
    more.append(bd, el("p", "small muted", ctx.goes_to_the_brain));

    const danger = el("div", "acts");
    danger.append(
      btn("Clear this chat", "btn", (e) => confirmTwice(e.target, "Really clear?", () => this.actions.clear())),
      btn("Delete this chat", "btn warn", (e) => confirmTwice(e.target, "Really delete?", () => this.actions.remove()))
    );
    more.append(danger);
    return more;
  }
}
