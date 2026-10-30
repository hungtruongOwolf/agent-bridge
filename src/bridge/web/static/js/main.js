/* The console starts here: the list of addresses (routes), which screen each one shows, and the few things every screen shares
   (the top bar, the coins chip, the front door). Each screen lives in views/ and knows nothing about the others except by address. */
import { $, el } from "./lib/dom.js";
import { Router } from "./lib/router.js";
import { bindRouter } from "./lib/nav.js";
import { refresh, subscribe } from "./lib/store.js";
import { toast } from "./lib/toast.js";
import { person } from "./pixel/office.js";
import { officeView } from "./views/office.js";
import { chatView } from "./views/chat.js";
import { studioView } from "./views/studio.js";
import { memoryView } from "./views/memory.js";
import { profileView } from "./views/profile.js";
import { walletView } from "./views/wallet.js";
import { earningsView } from "./views/earnings.js";
import { helpView } from "./views/help.js";
import { drawCoins } from "./components/coins.js";
import { setupFrontDoor } from "./components/front-door.js";
import { drawProposals } from "./components/proposals.js";

const memory = (mode) => ({ view: memoryView, data: { mode }, nav: "memory", title: "My memory" });

/* Every address the console understands. A path pattern uses :name for one part and *name for the rest. */
const ROUTES = [
  { path: "/", view: officeView, nav: "office", title: "My office" },
  { path: "/hire", view: officeView, data: { hire: true }, nav: "office", title: "Hire a helper" },
  { path: "/chats/:id", view: chatView, nav: "office", title: "Chat" },
  { path: "/helpers", view: studioView, nav: "studio", title: "My helpers" },
  { path: "/helpers/:id", view: studioView, nav: "studio", title: "My helpers" },
  { path: "/helpers/:id/:tab", view: studioView, nav: "studio", title: "My helpers" },
  { path: "/memory", ...memory("all") },
  { path: "/memory/shelf/*path", ...memory("shelf") },
  { path: "/memory/note/:id", ...memory("note") },
  { path: "/memory/trash", ...memory("trash") },
  { path: "/earnings", view: earningsView, nav: "earnings", title: "Earnings" },
  { path: "/market/:key", view: profileView, overlay: true, title: "Meet a helper" },
  { path: "/wallet", view: walletView, overlay: true, title: "Payments" },
  { path: "/help", view: helpView, overlay: true, title: "How this works" },
  { path: "/404", view: officeView, nav: "office", title: "My office" }
];

const VIEWS = [officeView, chatView, studioView, memoryView, profileView, walletView, earningsView, helpView];
let base = null;  // the full-page screen showing now
let overlay = null;  // the dialog showing on top of it, if any

function setSection(view) {
  ["view-office", "view-chat", "view-studio", "view-memory", "view-earnings"].forEach((id) => { $(id).hidden = id !== view.section; });
}

function markNav(name) {
  document.querySelectorAll("nav.tabs a").forEach((a) => {
    const on = a.dataset.nav === name;
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

async function onRoute({ route, params }, query, { initial }) {
  const data = { ...(route.data || {}), ...params };
  if (overlay && (!route.overlay || route.view !== overlay)) { overlay.leave(); overlay = null; }
  if (route.overlay) {
    if (!base) { base = officeView; setSection(base); markNav("office"); await base.enter({}, {}); }  // a dialog opened straight from a link: show the office under it
    overlay = route.view;
    await overlay.enter(data, query);
  } else {
    if (base && base !== route.view) base.leave();
    base = route.view;
    setSection(base);
    markNav(route.nav);
    await base.enter(data, query);
  }
  document.title = (route.title ? route.title + " · " : "") + "Agent Bridge";
  window.scrollTo(0, 0);
}

function drawLogo() {
  const c = $("logo").getContext("2d");
  c.imageSmoothingEnabled = false;
  c.fillStyle = "#FFF8E7";
  c.fillRect(0, 0, 22, 26);
  person(c, 11, 25, { pose: "idle", facing: "f", shirt: "#5CA97A", hat: "cap", skin: "#E0AC82", hair: "#1A1320" }, 0);
}

async function start() {
  let state0;
  try {
    state0 = await refresh();
    drawCoins(state0);
  } catch (e) {
    $("stalls").replaceChildren(el("p", "empty", "The console could not load: " + e.message + " Reload this page in a moment."));
    return;
  }
  VIEWS.forEach((v) => v.mount && v.mount());
  setupFrontDoor();
  drawLogo();
  const onState = (state) => {
    drawCoins(state);
    [officeView, chatView, memoryView].forEach((v) => v.redraw && v.redraw());
    const np = $("notespanel");
    np.hidden = !drawProposals($("notes"));
  };
  subscribe(onState);
  onState(state0);  // the state was loaded before anyone was listening: draw what is waiting (such as a helper's suggestion) now, not after the next change
  const router = new Router(ROUTES, (m, q, o) => onRoute(m, q, o).catch((e) => { console.error(e); toast("Something went wrong on this screen. Please try again.", true); }));
  bindRouter(router);
  router.start();
}

start();
