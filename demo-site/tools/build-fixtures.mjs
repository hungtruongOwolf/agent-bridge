/* Turns the raw recording (fixtures/trace.json) into the one file the replay reads (fixtures/replay.json).

     node demo-site/tools/build-fixtures.mjs

   The replay is a small state machine whose state is a "phase" that moves when the buyer does something:
     0 start   1 chat created   2 shelf ticked   3 first question asked (hold to approve)   4 first answer
     5 second question asked    6 second answer   7 second answer marked "not helpful"
   Pages that change as the story goes (state, office, the chat, its side panel, the receipts) are stored per phase.
   Everything else that is only read (memory, the studio, helper profiles, "how this answer was made") is stored once. */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const trace = JSON.parse(readFileSync(resolve(HERE, "../fixtures/trace.json"), "utf8")).filter((e) => !e.mark);

const VOLATILE = new Set(["/api/state", "/api/office", "/api/thread", "/api/thread/context", "/api/payments", "/api/threads"]);
const snaps = {};                       // path -> { phase: json }, the last one seen in that phase
const statics = {};                     // "path?sorted query" -> json
const posts = {};
const memory = { items: [] };
let phase = 0, sends = 0, conts = 0, settings = 0;

const keyOf = (e) => {
  const q = Object.entries(e.query).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => k + "=" + v).join("&");
  return e.path + (q ? "?" + q : "");
};

for (const e of trace) {
  if (e.method === "POST") {
    if (e.path === "/api/threads") { posts.threads = e.json; phase = 1; }
    else if (e.path === "/api/thread/settings") { if (!settings++) { posts.settings = e.json; phase = 2; } }
    else if (e.path === "/api/thread/send") { sends++; posts["send" + sends] = e.json; phase = sends === 1 ? 3 : 5; }
    else if (e.path === "/api/run/continue") { conts++; posts["cont" + conts] = e.json; phase = conts === 1 ? 4 : 6; }
    else if (e.path === "/api/thread/reject") { posts.reject = e.json; phase = 7; }
    continue;
  }
  if (e.status !== 200 || e.json === null) continue;
  if (e.path === "/api/memory" && e.query.limit === "100" && e.query.offset !== undefined) { memory.items.push(...e.json.items); continue; }
  if (VOLATILE.has(e.path)) { (snaps[e.path] ||= {})[phase] = e.json; continue; }
  if (e.path === "/api/thread/progress") continue;
  statics[keyOf(e)] = e.json;
}

// the chat as it stands in each phase (a reload in the middle of the story must show the same chat)
const thread = (j, over = {}) => ({ ...j, ...over });
snaps["/api/thread"] ||= {};
const T = snaps["/api/thread"];
T[1] = posts.threads;
T[2] = posts.settings;
T[3] = thread(posts.send1.thread, { busy: false });
T[4] = posts.cont1.thread;
T[5] = thread(posts.send2.thread, { busy: false });
T[6] = posts.cont2.thread;
T[7] = posts.reject;

memory.items = [...new Map(memory.items.map((i) => [i.id, i])).values()];   // the recorder sees its own extra fetches twice
const O = snaps["/api/office"];
for (let p = 3; p <= 6; p++) O[p] = O[7];                                   // the stall as it looks once the chat has a title and an answer

// receipts before the first answer: nothing held, nothing paid
const pay = snaps["/api/payments"];
const firstPay = pay[Math.min(...Object.keys(pay).map(Number))];
const zero = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, typeof v === "number" ? 0 : v]));
for (let p = 0; p <= 3; p++) pay[p] = { ...firstPay, summary: zero(firstPay.summary), items: [], plans: firstPay.plans };

// the prices that go to the approval card, and where the card's link points (a page of this site that imitates the practice PayPal page)
for (const k of ["send1", "send2"]) {
  const j = posts[k];
  j.approve_url = `/approve.html?run=${encodeURIComponent(j.run_id)}&price=${j.price}`;
}

const replay = { phases: 7, snaps, statics, posts, memory };
let text = JSON.stringify(replay);
text = text.split("http://127.0.0.1:8796/mock/state").join("/practice.html");     // the practice server's dashboard, as a page of this site
if (/127\.0\.0\.1|localhost/.test(text)) {
  const bad = text.match(/.{40}(127\.0\.0\.1|localhost).{40}/g);
  console.error("a local address is still in the replay:", bad && bad.slice(0, 3));
  process.exit(1);
}
writeFileSync(resolve(HERE, "../fixtures/replay.json"), text);
const kb = (Buffer.byteLength(text) / 1024).toFixed(0);
console.log(`replay.json: ${kb} KB, snapshots: ${Object.entries(snaps).map(([p, v]) => p + "[" + Object.keys(v).join(",") + "]").join(" ")}, static pages: ${Object.keys(statics).length}, notes: ${memory.items.length}`);
