/* The list of helpers for hire: a portrait, what they do, how much to trust them, the price, and Meet / Chat. */
import { person, lookFor } from "../pixel/office.js";
import { el, btn, link } from "../lib/dom.js";
import { niceName, plural } from "../lib/format.js";
import { paths } from "../lib/nav.js";
import { post } from "../lib/api.js";
import { blocked } from "../lib/store.js";
import { startChat } from "../lib/chats.js";

export function portrait(canvas, m) {
  const c = canvas.getContext("2d");
  c.imageSmoothingEnabled = false;
  c.fillStyle = "#F4E9C7";
  c.fillRect(0, 0, 22, 26);
  person(c, 11, 25, { pose: "idle", facing: "f", ...lookFor(m.id, m.status) }, 0);
}

export function pips(m) {
  const w = el("span", "pips" + (m.status === "certified" && m.score < 0.5 ? " warn" : ""));
  const n = m.status === "certified" ? Math.max(1, Math.round(m.score * 5)) : 0;
  for (let i = 0; i < 5; i++) w.append(el("i", i < n ? "on" : ""));
  return w;
}

export const trustText = (m) => (m.status !== "certified" ? "Not tested yet" : "Trust " + Math.round(m.score * 100) + " out of 100");

/** Draw every helper that may be chatted with, then a note about the ones that were caught cheating. */
export function renderHelperList(box, market) {
  box.replaceChildren();
  const ok = market.filter((m) => m.status !== "flagged");
  if (!ok.length) box.append(el("p", "empty", "Nobody is available yet."));
  ok.forEach((m) => {
    const row = el("div", "pick"), cv = el("canvas");
    cv.width = 22; cv.height = 26; cv.style.width = "44px"; cv.style.height = "52px";
    portrait(cv, m);
    const who = el("div", "who"), name = el("span", "name", niceName(m.id));
    name.append(el("span", "ver", " v" + m.version));
    who.append(name, el("span", "blurb", m.summary));
    const trust = el("div", "trust");
    trust.append(pips(m), el("span", null, trustText(m)));
    if (m.status === "certified") trust.append(el("span", "tag good", "#" + m.rank));
    who.append(trust, el("span", "blurb", "Price: " + m.price_text));
    const acts = el("div", "acts");
    acts.append(link(paths.helper(m.key), "Meet", "btn"), btn("Chat", "btn go2", () => startChat(m.key)));
    acts.append(btn("♥ " + m.stars + " fans", "fan", async () => {
      try { m.stars = (await post("/api/star", { key: m.key, user: "you" })).stars; renderHelperList(box, market); } catch (e) { /* liking is optional */ }
    }));
    row.append(cv, who, acts);
    box.append(row);
  });
  const flagged = market.filter((m) => m.status === "flagged");
  if (flagged.length) {
    box.append(el("p", "small muted", plural(flagged.length, "helper was", "helpers were") + " caught cheating in tests and cannot be chatted with:"));
    flagged.forEach((m) => {
      const reasons = [...new Set((m.violations || []).filter((v) => v !== "KILLED").map((v) => blocked(v) || v))];
      box.append(el("p", "small", niceName(m.id) + " " + (reasons.length ? reasons.join(", and ") + "." : "was caught cheating.")));
    });
  }
}
