/* One message of a conversation, with where it came from, how it was made, and what it cost. */
import { el, btn } from "../lib/dom.js";
import { get, url } from "../lib/api.js";
import { cents, plural } from "../lib/format.js";

function payLine(p) {
  if (p.state === "COVERED") return "Included in your monthly plan";
  if (p.state === "SETTLED") return "Paid " + cents(p.captured);
  if (p.state === "SETTLED_REJECTED") return "Marked not helpful, paid " + cents(p.captured);
  if (p.state === "RESULT_READY") return "Unless you press “Not helpful”, you pay the rest when you send your next message";
  return p.captured ? "Paid " + cents(p.captured) : "Not charged";
}

function filesDetails(m) {
  const f = el("details", "based");
  f.append(el("summary", null, "Written from " + m.files.length + " of your files"));
  f.addEventListener("toggle", async () => {
    if (!f.open || f.dataset.done) return;
    f.dataset.done = "1";
    try {
      const got = (await get(url("/api/memory", { limit: 100, ids: m.files.slice(0, 50).join(",") }))).items, by = new Map(got.map((r) => [r.id, r]));
      m.files.forEach((id) => {
        const r = by.get(id);
        f.append(el("div", "small", r ? r.shelf_name + ": " + (r.long ? "“" + r.title + "” (long note)" : r.text) : "A file you have since deleted"));
      });
    } catch (e) { f.append(el("div", "small muted", e.message)); }
  });
  return f;
}

function howDetails(runId) {
  const how = el("details", "based");
  how.append(el("summary", null, "How this answer was made"));
  how.addEventListener("toggle", async () => {
    if (!how.open || how.dataset.done) return;
    how.dataset.done = "1";
    try { (await get(url("/api/how", { run_id: runId }))).steps.forEach((t) => how.append(el("div", "small", "• " + t))); }
    catch (e) { how.append(el("div", "small muted", e.message)); }
  });
  return how;
}

/** `act(path, body)` runs a change on this chat (reject, forget) and redraws. */
export function bubble(m, chatId, act) {
  const d = el("div", "msg " + m.role);
  d.append(el("div", "text", m.text));
  const meta = el("div", "meta small muted");
  if (m.role === "helper") {
    if (m.risk) meta.append(el("span", "tag " + (m.risk === "high" ? "bad" : m.risk === "medium" ? "wait" : "good"), "worry level: " + m.risk), " ");
    if (m.files && m.files.length) d.append(filesDetails(m));
    else meta.append("Written without any of your files. ");
    if (m.run_id) d.append(howDetails(m.run_id));
    if (m.proposals) meta.append(plural(m.proposals, "suggestion") + " to remember " + (m.proposals === 1 ? "is" : "are") + " waiting under My office. ");
  }
  if (m.payment) {
    meta.append(payLine(m.payment));
    if (m.payment.can_reject) meta.append(" ", btn("Not helpful", "linkbtn", () => act("/api/thread/reject", { id: chatId, message_id: m.id })));
  }
  if (m.role !== "system" || !m.run_id) meta.append(" ", btn("Forget this message", "linkbtn", () => act("/api/thread/forget", { id: chatId, message_id: m.id })));
  if (meta.childNodes.length) d.append(meta);
  return d;
}
