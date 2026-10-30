/* Payments: what was spent, what is on hold, every receipt in plain words, and the monthly plans (with a way to stop each one). /wallet */
import { el, btn } from "../lib/dom.js";
import { get, post } from "../lib/api.js";
import { cents, when, day } from "../lib/format.js";
import { overlay } from "../lib/overlay.js";

export const MODE = {
  test: { short: "Coins", name: "Demo coins", line: "These are demo coins kept in a file. Nothing real moves anywhere." },
  "paypal-mock": { short: "PayPal (practice)", name: "Practice PayPal", line: "A practice server on this computer behaves like the PayPal sandbox, including the approval page. It is not PayPal and no real money is involved." },
  "paypal-sandbox": { short: "PayPal sandbox", name: "PayPal sandbox", line: "Test money on PayPal's sandbox. You approve each hold on PayPal's own page. No real money moves." }
};

function planCard(p, again) {
  const row = el("div", "receipt"), top = el("div", "rtop");
  top.append(el("b", null, p.helper), el("span", "small muted", p.pending ? "starts when the first answer is accepted" : p.running ? "until " + day(p.until) : "finished"));
  row.append(top, el("div", "small", p.pending ? "Waiting for the first payment to settle." : `${p.used} of ${p.included} answers used, ${p.left} left. It does not renew by itself.`));
  if (p.running) row.append(btn("Stop this plan", "linkbtn", async () => { try { await post("/api/subscription/cancel", { key: p.key }); again(); } catch (e) { /* the list stays as it was */ } }));
  return row;
}

function receipt(r) {
  const c = el("div", "receipt"), top = el("div", "rtop"), parts = ["Price " + cents(r.price)];
  top.append(el("b", null, r.helper + (r.chat ? " · " + r.chat : "")), el("span", "small muted", when(r.when)));
  if (r.captured) parts.push("charged " + cents(r.captured));
  if (r.refunded) parts.push("given back " + cents(r.refunded));
  if (r.payout.amount) parts.push("author gets " + cents(r.payout.amount) + (r.payout.status === "paid" ? " (paid)" : " (pending)"));
  const det = el("details", "more");
  det.append(el("summary", null, "What happened"));
  r.events.forEach((e) => det.append(el("div", "small", when(e.t) + " · " + e.to + (e.why ? " (" + e.why + ")" : ""))));
  if (r.reference) det.append(el("div", "small muted", "Reference: " + r.reference));
  c.append(top, el("div", "small", r.state_text), el("div", "small muted", parts.join(" · ")), det);
  return c;
}

async function render(_, body) {
  body.replaceChildren(el("p", null, "Loading…"));
  let d;
  try { d = await get("/api/payments"); } catch (e) { body.replaceChildren(el("p", null, e.message)); return; }
  const m = MODE[d.mode] || MODE.test, s = d.summary;
  body.replaceChildren(el("h2", null, m.name), el("p", null, m.line));
  if (d.dashboard) {
    const a = el("a", "btn", "Open the practice PayPal page");
    a.href = d.dashboard; a.target = "_blank"; a.rel = "noopener noreferrer";
    const acts = el("div", "acts");
    acts.append(a);
    body.append(acts);
  }
  const sum = el("div", "walletsum");
  [["Spent", cents(s.captured || 0)], ["On hold", cents(s.on_hold || 0)], ["Paid to helper authors", cents(s.paid_out || 0)]].forEach(([k, v]) => {
    const c = el("div", "wcell");
    c.append(el("div", "small muted", k), el("b", null, v));
    sum.append(c);
  });
  body.append(sum);
  if (d.plans && d.plans.length) {
    body.append(el("h3", "sub", "Monthly plans"));
    d.plans.forEach((p) => body.append(planCard(p, () => render(_, body))));
  }
  body.append(el("h3", "sub", "Receipts"));
  if (!d.items.length) body.append(el("p", "empty", "No payments yet. Money only moves after you start a chat message."));
  d.items.forEach((r) => body.append(receipt(r)));
}

export const walletView = overlay("wallet", render);
