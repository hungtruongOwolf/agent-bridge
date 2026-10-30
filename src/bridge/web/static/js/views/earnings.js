/* Earnings: what your helpers earned, and what you spent on other helpers, as a table you can sort and filter, with a chart of each run.
   Built on AG Grid and AG Charts (Community editions, MIT, vendored in static/vendor so it works offline). /earnings */
import { $, el, btn } from "../lib/dom.js";
import { get } from "../lib/api.js";
import { cents, when } from "../lib/format.js";

const LIBS = [["/static/vendor/ag-grid/ag-grid-community.min.nostyle.js", () => window.agGrid], ["/static/vendor/ag-charts/ag-charts-community.min.js", () => window.agCharts]];
let loading = null, data = null, tab = "earned", grid = null, chart = null;

function load() {
  loading = loading || Promise.all(LIBS.map(([src, ready]) => new Promise((ok, no) => {
    if (ready()) return ok();
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => no(new Error("The table library could not be loaded."));
    document.head.append(s);
  })));
  return loading;
}

const CSS = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const money = (p) => (p.value === null || p.value === undefined ? "" : cents(p.value));
const STATUS_TONE = { "Paid": "--mint-light", "Deposit only": "--lemon-light", "Refunded": "--coral-light", "On hold": "--sky-light", "Waiting": "--lilac-light" };
let registered = false;

function theme() {
  const g = window.agGrid;
  if (!registered) { g.ModuleRegistry.registerModules([g.AllCommunityModule]); registered = true; }
  return g.themeQuartz.withParams({
    fontFamily: CSS("--ui"), fontSize: 14, headerFontFamily: CSS("--ui"), headerFontWeight: 700,
    backgroundColor: CSS("--cream-50"), foregroundColor: CSS("--ink-900"), headerBackgroundColor: CSS("--cream-200"), headerTextColor: CSS("--ink-900"),
    borderColor: CSS("--ink-300"), accentColor: CSS("--mint"), oddRowBackgroundColor: CSS("--cream-100"), rowHoverColor: CSS("--mint-light"),
    selectedRowBackgroundColor: CSS("--mint-light"), borderRadius: 0, wrapperBorderRadius: 0, spacing: 6, browserColorScheme: "light"
  });
}

function columns() {
  const num = (field, headerName, extra) => ({ field, headerName, filter: "agNumberColumnFilter", valueFormatter: money, type: "rightAligned", width: 130, ...extra });
  return [
    { field: "when", headerName: "Date", width: 140, filter: "agDateColumnFilter", valueFormatter: (p) => when(p.value), sort: "desc",
      filterValueGetter: (p) => new Date(p.data.when * 1000) },
    { field: "helper", headerName: "Helper", filter: "agTextColumnFilter", width: 140 },
    { field: "plan", headerName: "Plan", filter: "agTextColumnFilter", width: 104 },
    num("hold", "Held (most)", { headerTooltip: "The most this run could cost, held until it finished", width: 130 }), num("price", "Price"), num("charged", "Charged"),
    num("author_payout", "Author gets"), num("platform_fee", "Platform fee"), num("released", "Given back"),
    { field: "status", headerName: "Status", filter: "agTextColumnFilter", width: 124,
      cellStyle: (p) => ({ background: `var(${STATUS_TONE[p.value] || "--cream-100"})`, fontWeight: 600 }) },
    { field: "receipt", headerName: "Receipt", filter: "agTextColumnFilter", minWidth: 110, flex: 1, tooltipField: "receipt" }
  ];
}

function summary(rows, totals) {
  const box = el("div", "earnsum");
  const cell = (k, v) => { const c = el("div", "wcell"); c.append(el("div", "small muted", k), el("b", null, v)); return c; };
  if (tab === "earned") box.append(cell("Runs", String(totals.runs)), cell("Charged to buyers", cents(totals.charged)), cell("You get", cents(totals.author_payout)), cell("Platform fee", cents(totals.platform_fee)));
  else box.append(cell("Runs", String(totals.runs)), cell("Charged", cents(totals.charged)), cell("Given back", cents(totals.released)), cell("Still on hold", cents(rows.filter((r) => r.status === "On hold").reduce((a, r) => a + r.hold, 0))));
  const by = new Map();
  rows.forEach((r) => { const b = by.get(r.helper) || { helper: r.helper, runs: 0, charged: 0, payout: 0 }; b.runs++; b.charged += r.charged; b.payout += r.author_payout; by.set(r.helper, b); });
  const list = el("div", "byhelper");
  list.append(el("span", "small muted", "By helper:"));
  [...by.values()].sort((a, b) => b.charged - a.charged).forEach((b) => {
    const c = el("span", "chip");
    c.textContent = `${b.helper}: ${b.runs} ${b.runs === 1 ? "run" : "runs"}, ${cents(b.charged)}` + (tab === "earned" ? `, you get ${cents(b.payout)}` : "");
    list.append(c);
  });
  return [box, list];
}

function clear() {
  if (grid) { grid.destroy(); grid = null; }
  if (chart) { chart.destroy(); chart = null; }
}

function draw() {
  const body = $("earnbody");
  clear();
  const part = data[tab], rows = part.rows;
  body.replaceChildren();
  if (!rows.length) {
    body.append(el("p", "empty", tab === "earned" ? "No one has paid for a helper you built yet. When someone does, each run shows up here." : "You have not spent anything yet. Payments appear here after you send a message to a helper."));
    return;
  }
  body.append(...summary(rows, part.totals));
  const cwrap = el("div", "earnchart"), gwrap = el("div", "earngrid");
  cwrap.setAttribute("role", "img"); cwrap.setAttribute("aria-label", "One bar for each run. It shows what the author was paid, the platform fee, and the part of the hold that was given back.");
  body.append(el("h3", "sub", "Each run"), cwrap, el("h3", "sub", "Every payment"), gwrap);
  const recent = rows.slice(0, 12).reverse().map((r, i) => ({ run: `${i + 1}. ${r.helper} (${when(r.when)})`, payout: r.author_payout, fee: r.platform_fee, released: r.released }));
  const font = { fontFamily: CSS("--ui") };
  chart = window.agCharts.AgCharts.create({
    container: cwrap, data: recent, height: 280, background: { fill: CSS("--cream-50") },
    theme: { palette: { fills: [CSS("--mint"), CSS("--coral"), CSS("--sky")], strokes: [CSS("--ink-900"), CSS("--ink-900"), CSS("--ink-900")] } },
    series: [
      { type: "bar", xKey: "run", yKey: "payout", yName: "Paid to the author", stacked: true, strokeWidth: 1.5 },
      { type: "bar", xKey: "run", yKey: "fee", yName: "Platform fee", stacked: true, strokeWidth: 1.5 },
      { type: "bar", xKey: "run", yKey: "released", yName: "Given back (never charged)", stacked: true, strokeWidth: 1.5 }
    ],
    axes: [{ type: "category", position: "bottom", label: { ...font, fontSize: 11, rotation: -30 } },
      { type: "number", position: "left", label: { ...font, formatter: (p) => cents(p.value) } }],
    legend: { position: "bottom", item: { label: font } }
  });
  gwrap.style.height = 56 + 37 * Math.min(rows.length, 10) + 60 + "px";  // header, the rows of one page, and the page bar
  grid = window.agGrid.createGrid(gwrap, {
    theme: theme(), rowData: rows, columnDefs: columns(), pagination: true, paginationPageSize: 10, paginationPageSizeSelector: [10, 25, 50],
    defaultColDef: { sortable: true, resizable: true, filter: true }, animateRows: false,
    localeText: { noRowsToShow: "Nothing matches." }, tooltipShowDelay: 300
  });
}

function setTab(t) {
  tab = t;
  document.querySelectorAll("#earntabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === t)));
  if (data) draw();
}

export const earningsView = {
  section: "view-earnings",
  mount() {
    const tabs = $("earntabs");
    [["earned", "Helpers I built"], ["spent", "My spending"]].forEach(([k, label]) => { const b = btn(label, null, () => setTab(k)); b.dataset.tab = k; b.setAttribute("role", "tab"); tabs.append(b); });
  },
  async enter() {
    $("earnnote").textContent = "";
    try { [data] = await Promise.all([get("/api/earnings"), load()]); } catch (e) { $("earnnote").textContent = e.message; return; }
    setTab(tab);
  },
  leave() { clear(); },
  redraw() {}
};
