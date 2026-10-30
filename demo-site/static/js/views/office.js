/* My office: the market floor. One stall per chat, all on one picture, plus the market square (guard, bank, library) and, when
   asked for (/hire) or when there are no chats yet, the list of helpers to open a new stall with. */
import { $, el, btn, link } from "../lib/dom.js";
import { get } from "../lib/api.js";
import { getState } from "../lib/store.js";
import { cents, plural } from "../lib/format.js";
import { paths } from "../lib/nav.js";
import { person } from "../pixel/office.js";
import { stallCard } from "../components/stall.js";
import { renderHelperList } from "../components/helpers.js";

let timer = null, last = "", hire = false, floor = null;

function icon(look) {
  const cv = el("canvas");
  cv.width = 22; cv.height = 26; cv.className = "sqicon";
  cv.setAttribute("aria-hidden", "true");
  const c = cv.getContext("2d");
  c.imageSmoothingEnabled = false;
  c.fillStyle = "#F4E9C7";
  c.fillRect(0, 0, 22, 26);
  person(c, 11, 25, { pose: "idle", facing: "f", ...look }, 0);
  return cv;
}

function squareCard(look, title, lines, extra) {
  const card = el("div", "sqcard"), text = el("div", "sqtext");
  text.append(el("div", "sqtitle", title));
  lines.forEach((l) => text.append(el("div", "small", l)));
  if (extra) text.append(extra);
  card.append(icon(look), text);
  return card;
}

/** The market square: the shared places every stall depends on. */
function drawSquare(d) {
  const sq = $("square"), pay = getState().payments || { captured: 0, on_hold: 0 }, n = d.stalls.length;
  const panel = el("div", "panel"), body = el("div", "body sqbody");
  panel.append(el("div", "title", "The market square"), body);
  if (hire) body.append(link(paths.office(), "Hide the list of helpers", "btn sqwide"));  // opening a stall is the dashed stall on the floor
  body.append(squareCard({ shirt: "#3D2E4A", hat: "guard", skin: "#E0AC82", hair: "#1A1320" }, "Guard post",
    [d.guard.stopped ? "Stopped " + plural(d.guard.stopped, "sneaky attempt") + "." : "Nothing suspicious so far.", "Checks every answer before it reaches you."]));
  body.append(squareCard({ shirt: "#DCAB3C", hat: "visor", skin: "#C68642", hair: "#3B2A20" }, "Bank",
    ["Spent on answers: " + cents(pay.captured || 0), "On hold for you: " + cents(pay.on_hold || 0), "Nothing is charged until a helper answers."]));
  body.append(squareCard({ shirt: "#9482D3", hat: "glasses", skin: "#F5CBA7", hair: "#8A5A2B" }, "Library",
    [plural(d.memory.total, "note") + " on shelves", d.memory.secret ? d.memory.secret + " secret, never shared" : "No secret notes yet"], link(paths.memory(), "Open my memory", "btn")));
  body.append(el("p", "small muted", n ? plural(n, "chat") + " open" + (d.working ? ", " + d.working + " working now." : ".") : "No chats yet."));
  sq.replaceChildren(panel);
}

function drawWelcome(n) {
  let hidden = false;
  try { hidden = localStorage.getItem("ab-welcome") === "1"; } catch (e) { /* the card just shows again */ }
  $("welcome").hidden = n > 0 || hidden;
}

function draw(d) {
  drawSquare(d);
  drawWelcome(d.stalls.length);
  floor.hidden = !d.stalls.length;  // no chats yet: just the welcome and the list of helpers
  const box = $("stalls");
  box.replaceChildren(...d.stalls.map(stallCard));
  const add = link(paths.hire(), "", "stall newstall");
  add.append(el("div", "plus", "+"), el("div", "sname", "Open a new stall"), el("div", "sline", "Pick a helper and start a conversation."));
  box.append(add);
  $("hirepanel").hidden = !(hire || !d.stalls.length);
}

async function poll() {
  if (document.hidden) return;
  try {
    const d = await get("/api/office"), sig = JSON.stringify(d);
    if (sig !== last) { last = sig; draw(d); }
  } catch (e) { /* the next poll tries again */ }
}

export const officeView = {
  section: "view-office",

  mount() {
    floor = document.querySelector(".floorgrid");
    $("welcomehide").onclick = () => { try { localStorage.setItem("ab-welcome", "1"); } catch (e) { /* optional */ } $("welcome").hidden = true; };
  },

  enter({ hire: wantHire }) {
    hire = !!wantHire;
    last = "";
    this.redraw();
    clearInterval(timer);
    timer = setInterval(poll, 1500);
    poll();
    if (hire) $("hirepanel").scrollIntoView({ block: "nearest" });
  },

  leave() {
    clearInterval(timer);
    timer = null;
  },

  /** The shared state changed (a helper was liked, memory changed, money moved). */
  redraw() {
    if ($("view-office").hidden) return;
    renderHelperList($("picker"), getState().market);
    last = "";
    poll();
  }
};
