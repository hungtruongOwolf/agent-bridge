/* n05 (version 2): Ask and see what left the room. A new chat with Deal Brief, Work > Accounts ticked (set up before recording),
   the question typed, the little office acting out the run, the answer with its notes, and "How this answer was made".
   The answer is made live by Nemotron on Nebius, so the wait is real; the edit speeds up the marked wait. */
import { sleep } from "../recorder.mjs";

const soft = async (f) => { try { await f(); } catch (e) { console.error("skipped:", e.message); } };

export default async function (rec) {
  await rec.goto("/");
  await sleep(700);
  await rec.click("a.stall.newstall", null, { after: 700 });
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.click(".pick .btn.go2", "Chat", { nth: 2, after: 1000 });                // Deal Brief
  await rec.waitFor(() => location.pathname.startsWith("/chats/"));
  await sleep(600);
  await rec.scrollTo("#sidepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 500 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Accounts", "input[type=checkbox]"), { after: 500 });
  await rec.scrollTo();
  await sleep(500);
  await rec.start("n05");
  await rec.click("#draft", null, { after: 250 });
  await rec.type("Which accounts are at risk this quarter, and who was Acme's old billing contact?", { delay: 36 });
  await sleep(350);
  rec.mark("send");
  await rec.click("#send", null, { after: 400 });
  await soft(async () => { const office = await rec.find("#sidepanel, .office, canvas"); await rec.cam(await rec.find("canvas", null), 1.5, { ms: 1200, dx: 360, dy: 0 }); });
  await sleep(3200);                                                                  // the office acts out the run: hold on it a while
  await rec.waitFor(() => document.querySelectorAll("#convo .msg.helper:not(.thinking), #convo .msg.system").length >= 1, { timeout: 120000 });
  rec.mark("answer");
  await rec.camReset(800);
  await sleep(1800);
  await soft(async () => { const b = await rec.find("#convo details.based summary", "Written from"); await rec.ring(b, "The notes it used"); await rec.clickEl(b, { after: 2200 }); });
  await rec.unring();
  rec.mark("based");
  await soft(async () => { const h = await rec.find("#convo details.based summary", "How this answer was made"); await rec.clickEl(h, { after: 800 }); await rec.cam(h, 1.3, { ms: 1000, dy: -140 }); });
  await soft(async () => { const l = await rec.findText("Sent", { part: true, within: "#convo" }); await rec.ring(l, "What went to the model"); });
  await sleep(3000);
  await soft(async () => { await rec.unring(); const l = await rec.findText("swapped for a placeholder", { part: true, within: "#convo" }); await rec.ring(l, "Placeholders, restored on my machine"); });
  await sleep(3200);
  rec.mark("how");
  await rec.page.screenshot({ path: "../../video-out/shot-n05-how.png" });
  await rec.camReset(500);
  await rec.stop();
}
