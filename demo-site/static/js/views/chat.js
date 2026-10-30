/* One chat = one small office. The conversation, the composer with its hints, the approval step for a payment, and the
   side panel that shows (and changes) what the helper may see. Everything the person did is saved by the server, so the
   address /chats/<id> always opens the same chat. */
import { $, el, btn, debounce } from "../lib/dom.js";
import { get, post, url } from "../lib/api.js";
import { refresh } from "../lib/store.js";
import { navigate, paths } from "../lib/nav.js";
import { cents, day } from "../lib/format.js";
import { toast } from "../lib/toast.js";
import { MiniOffice } from "../components/mini-office.js";
import { SidePanel } from "../components/sidepanel.js";
import { bubble } from "../components/bubble.js";

let chat = null;  // the open chat, as the server describes it
let ctx = null;  // the latest "what the helper will see" preview
let ctxKey = "";
let sending = false, sendingId = null, pendingText = "", progress = [], progressTimer = null;
let approval = null;  // {threadId, text, run_id, approve_url, price}: a message waiting for the buyer to approve the hold
let office = null, side = null;

const note = (t) => { $("chatnote").textContent = t || ""; };
const isHere = (id) => chat && chat.id === id;
const waiting = () => (approval && chat && approval.threadId === chat.id) || (sending && chat && sendingId === chat.id);

function planLine(a) {
  if (a.plan_status) return `monthly plan until ${day(a.plan_status.until)}, ${a.plan_status.left} of ${a.plan_status.included} answers left`;
  return a.price_text;
}

/* ---------- the conversation ---------- */
function userBubble(text) {
  const u = el("div", "msg user");
  u.append(el("div", "text", text));
  return u;
}

function drawConversation() {
  const box = $("convo");
  box.replaceChildren();
  $("composer").hidden = !chat;
  $("sidepanel").hidden = !chat;
  if (!chat) { $("budgetline").textContent = ""; note(""); $("convohead").replaceChildren(); return; }
  const a = chat.agent, head = $("convohead"), title = el("div"), acts = el("div", "acts");
  title.append(el("div", "h", chat.title), el("div", "muted small", a.available ? "with " + a.name + " · " + planLine(a) : "This helper is no longer available."));
  if (a.available) { const meet = el("a", "btn", "Meet " + a.name); meet.href = paths.helper(a.key); meet.dataset.link = ""; acts.append(meet); }
  head.replaceChildren(title, acts);

  if (!chat.messages.length) box.append(el("p", "empty", "Type your question below. Tick a shelf on the left if the helper should use your files."));
  chat.messages.forEach((m) => box.append(bubble(m, chat.id, act)));
  if (approval && approval.threadId === chat.id) {
    if (approval.text) box.append(userBubble(approval.text));
    box.append(approvalCard());
  }
  if (sending && sendingId === chat.id) {
    if (pendingText) box.append(userBubble(pendingText));
    const w = el("div", "msg helper thinking");
    w.id = "workbubble";
    w.append(el("div", "text", "Working on it…"), el("div", "small muted", progress.join(" ")));
    box.append(w);
  }
  box.scrollTop = box.scrollHeight;
  if (chat.busy && !waiting()) {
    const r = el("div", "msg system");
    r.append(el("div", "text", "This chat still looks busy, maybe because the page was reloaded."), btn("Reset this chat", "btn", resetBusy));
    box.append(r);
  }
  $("send").disabled = !!waiting() || chat.busy || !a.available;
  const b = chat.budget;
  $("budgetline").textContent = `Spent so far: ${cents(b.spent)}${b.held ? ` (+${cents(b.held)} on hold)` : ""} of ${cents(b.limit)}.`;
}

async function reload() {
  if (!chat) return;
  chat = await get(url("/api/thread", { id: chat.id }));
}

async function act(path, body) {
  try {
    const r = await post(path, body);
    if (r.messages) chat = r; else await reload();
    await refresh();
    drawConversation();
    loadContext();
  } catch (e) { note(e.message); }
}

async function resetBusy() {
  try { await post("/api/thread/settings", { id: chat.id, reset_busy: true }); await reload(); drawConversation(); } catch (e) { note(e.message); }
}

/* ---------- sending ---------- */
async function send(ev) {
  ev.preventDefault();
  const box = $("draft"), text = box.value.trim();
  if (!chat || sending || !text) return;
  const mine = chat.id;
  sending = true; sendingId = mine; pendingText = text; progress = [];
  note(""); drawConversation(); watchProgress(mine);
  office.working(chat.agent, ctx && ctx.shelves);
  let report = null;
  try {
    const r = await post("/api/thread/send", { id: mine, text, simulate: false });
    box.value = "";
    if (r.needs_approval) { approval = { threadId: mine, text, ...r }; office.caption("Waiting for you to approve the hold on the payment page."); }
    if (isHere(mine)) chat = r.thread;
    report = r.report || null;
  } catch (e) {
    note(e.message);
    try { const t = await get(url("/api/thread", { id: mine })); if (isHere(mine)) chat = t; } catch (_) { /* keep what is on screen */ }
  }
  sending = false; sendingId = null; pendingText = "";
  clearInterval(progressTimer);
  try { await refresh(); } catch (_) { /* the screen already shows the answer */ }
  drawConversation(); loadContext();
  if (report && isHere(mine)) office.replay(report, () => isHere(mine));
}

function watchProgress(id) {
  clearInterval(progressTimer);
  progressTimer = setInterval(async () => {
    if (!sending || sendingId !== id) { clearInterval(progressTimer); return; }
    try {
      const p = await get(url("/api/thread/progress", { id }));
      progress = p.steps;
      const w = $("workbubble");
      if (w && w.lastChild) w.lastChild.textContent = p.steps.length ? p.steps[p.steps.length - 1] : "";
      if (p.steps.length) office.caption(p.steps[p.steps.length - 1]);
    } catch (e) { /* the answer itself will report problems */ }
  }, 900);
}

/* ---------- paying: the buyer approves a hold on the provider's page ---------- */
async function continueApproved() {
  const p = approval;
  if (!p || sending) return;
  sending = true; sendingId = p.threadId; drawConversation();
  let report = null;
  try {
    const r = await post("/api/run/continue", { run_id: p.run_id });
    approval = null;
    if (isHere(p.threadId)) chat = r.thread;
    report = r.report;
  } catch (e) { note(e.message + " If this keeps happening, press Cancel and send the message again."); }
  sending = false; sendingId = null;
  try { await refresh(); } catch (_) { /* optional */ }
  drawConversation(); loadContext();
  if (report && isHere(p.threadId)) office.replay(report, () => isHere(p.threadId));
}

function approvalCard() {
  const p = approval, d = el("div", "msg system"), ag = chat.agent;
  const what = ag.subscription ? `This helper sells a monthly plan (${ag.price_text}). Approve a hold of ${cents(p.price)} on the payment page to start it.`
    : ag.metered ? `Approve a hold of ${cents(p.price)} on the payment page. That is the most this answer can cost; you pay only for what it uses.`
    : `Before the helper starts, approve a hold of ${cents(p.price)} on the payment page.`;
  d.append(el("div", "text", what + " Nothing is charged until there is an answer."));
  const acts = el("div", "acts");
  if (/^https?:\/\//.test(p.approve_url || "")) {
    const a = el("a", "btn go2", "Open the approval page");
    a.href = p.approve_url; a.target = "_blank"; a.rel = "noopener noreferrer";
    acts.append(a);
  }
  acts.append(btn("I approved, continue", "btn", continueApproved), btn("Cancel", "btn warn", async () => {
    try { await post("/api/thread/cancel", { run_id: p.run_id }); } catch (e) { note(e.message); }
    approval = null;
    try { await reload(); await refresh(); } catch (_) { /* optional */ }
    drawConversation();
  }));
  d.append(acts, el("div", "small muted", "When you approve on the other page, this chat carries on by itself."));
  return d;
}

/** The approval page tells this tab when the buyer is done, so the chat can carry on by itself. */
function listenForApproval() {
  const onMsg = (what) => {
    if (what === "approved" && approval) continueApproved();
    else if (what === "cancelled" && approval) note("The hold was cancelled on the payment page. Press Cancel here, then send your message again.");
  };
  try { new BroadcastChannel("agent-bridge-paypal").onmessage = (e) => onMsg(e.data); } catch (e) { /* older browsers use the storage event */ }
  window.addEventListener("storage", (e) => { if (e.key === "agent-bridge-paypal" && e.newValue) onMsg(String(e.newValue).split(":")[0]); });
}

/* ---------- what the helper will see ---------- */
async function loadContext() {
  if (!chat) return;
  const mine = chat.id;
  try {
    const c = await get(url("/api/thread/context", { id: mine, draft: $("draft").value.slice(0, 300) }));
    if (!isHere(mine)) return;
    const key = JSON.stringify([c.shelves.map((s) => [s.path, s.state, s.count, s.shared]), c.shared.map((f) => f.id), c.held_back.map((f) => f.id), c.likely, c.walk, c.suggest, c.history.length, chat.lens, chat.history_turns, chat.budget.limit]);
    const changed = key !== ctxKey;
    ctx = c; ctxKey = key;
    if (changed) { side.render(chat, ctx); drawHint(); office.setDrawers(ctx.shelves); }
  } catch (e) { note(e.message); }
}

function drawHint() {
  const h = $("hint");
  h.replaceChildren();
  if (!chat) return;
  if (!chat.lens.shelves.length && !chat.lens.include.length) h.append(el("span", "small muted", "No shelf is ticked, so it will answer from your message alone."));
  (ctx.suggest || []).forEach((s) => {
    const row = el("span", "suggestion");
    row.append(el("span", "small", `This may need “${s.name}”. `), btn("Tick it", "btn go2", () => side.openShelf(chat, s.path)));
    h.append(row);
  });
}

async function setSettings(patch) {
  ctxKey = "";
  try {
    chat = await post("/api/thread/settings", { id: chat.id, ...patch });
    await refresh();
    drawConversation();
    await loadContext();
  } catch (e) { note(e.message); await loadContext(); }
}

/* ---------- the view ---------- */
export const chatView = {
  section: "view-chat",

  mount() {
    office = new MiniOffice({ canvas: $("floor"), caption: $("caption"), title: $("officetitle"), onDrawer: (path) => chat && ctx && side.toggleShelf(chat, ctx, path) });
    side = new SidePanel($("sidebody"), {
      settings: setSettings,
      clear: () => act("/api/thread/clear", { id: chat.id }),
      remove: async () => { try { await post("/api/thread/delete", { id: chat.id }); chat = null; await refresh(); navigate(paths.office()); } catch (er) { note(er.message); } }
    });
    $("composer").onsubmit = send;
    $("draft").oninput = debounce(loadContext, 350);
    $("draft").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); } };
    listenForApproval();
  },

  async enter({ id }, query) {
    office.ensure();
    if (!chat || chat.id !== id) {
      chat = null; ctx = null; ctxKey = "";
      drawConversation();
      try { chat = await get(url("/api/thread", { id })); }
      catch (e) { toast(e.message, true); navigate(paths.office(), { replace: true }); return; }
    } else await reload();
    if (approval && approval.threadId !== chat.id) approval = null;
    drawConversation();
    office.show(chat.agent, ctx && ctx.shelves);
    office.caption(chat.messages.length ? "Here is what the helper just did." : "Waiting for your question.");
    if (query.draft) {  // a question brought here by the front door or a profile: typed in, never sent for you
      $("draft").value = query.draft;
      history.replaceState({}, "", paths.chat(id));
    }
    await loadContext();
    $("draft").focus();
    office.resize();
  },

  leave() {
    clearInterval(progressTimer);
  },

  /** The shared state changed elsewhere (money moved): refresh the cost line. */
  redraw() {
    if (chat && !$("view-chat").hidden) drawConversation();
  }
};

