/* Meet a helper: what it says it can do, what it touches, and how it did in the tester's questions. /market/<key> */
import { el, btn } from "../lib/dom.js";
import { get, url } from "../lib/api.js";
import { blocked } from "../lib/store.js";
import { niceName } from "../lib/format.js";
import { overlay } from "../lib/overlay.js";
import { startChat } from "../lib/chats.js";

async function render({ key }, body) {
  body.replaceChildren(el("p", null, "Loading…"));
  let p;
  try { p = await get(url("/api/agent", { key })); } catch (e) { body.replaceChildren(el("p", null, e.message)); return; }
  const name = niceName(p.id), m = p.measured;
  body.replaceChildren(el("h2", null, "Meet " + name), el("p", null, p.summary));
  if (p.speciality) body.append(el("p", "muted", "Best at: " + p.speciality));
  body.append(el("p", "small", `${p.price_text} · ${p.stars} fans · version ${p.version}`), el("h3", "sub", "What it can do"));

  p.author_says.skills.forEach((s) => {
    const d = el("div", "skill"), q = el("div", "small muted");
    d.append(el("div", "name", s.name), el("div", null, s.does));
    q.append("Try asking: ");
    (s.try_asking || []).forEach((t) => q.append(btn("“" + t + "”", "linkbtn", async () => { await startChat(key, t); }), " "));
    d.append(q);
    body.append(d);
  });
  if (p.author_says.good_to_know && p.author_says.good_to_know.length) {
    const ul = el("ul");
    p.author_says.good_to_know.forEach((t) => ul.append(el("li", null, t)));
    body.append(el("h3", "sub", "Good to know"), ul);
  }

  const safety = el("details", "more"), touches = el("ul"), never = el("ul");
  safety.append(el("summary", null, "What it touches and what it can never do"));
  p.works_with.forEach((x) => touches.append(el("li", null, x.text)));
  p.cannot.forEach((x) => never.append(el("li", null, x)));
  safety.append(touches, never);
  body.append(safety, el("h3", "sub", "How well it did in tests"));

  if (!m.tested) body.append(el("p", null, m.note));
  else if (m.violations) body.append(el("p", "tag bad", "Caught cheating during testing: " + m.violations.map((v) => blocked(v) || v).join("; ")));
  else {
    body.append(el("p", null, `Passed ${m.passes} of ${m.total} test questions. How much to trust it: ${m.score} out of 100.` + (m.infra_failures ? ` ${m.infra_failures} run(s) were thrown out because the thinking service was down.` : "")));
    m.by_skill.forEach((s) => {
      const r = el("div", "skillrow");
      r.append(el("span", null, s.what), el("b", null, `${s.passes} of ${s.total}`));
      body.append(r);
      if (s.ask) body.append(el("div", "small muted", "Test question: “" + s.ask + "”"));
    });
  }
  body.append(el("div", "acts", ""), btn("Chat with " + name, "btn go2", () => startChat(key)));
}

export const profileView = overlay("profile", render);
