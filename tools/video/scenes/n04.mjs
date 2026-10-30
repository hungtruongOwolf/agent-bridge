/* n04 (version 2): My memory. The map and its count, the tick panel of a chat, and the secret shelves. Timed to a voice of about 14 seconds. */
import { sleep } from "../recorder.mjs";

const soft = async (f) => { try { await f(); } catch (e) { console.error("skipped:", e.message); } };

export default async function (rec) {
  await rec.goto("/");
  const chat = await rec.chatPath("Weekly account review");
  await rec.goto("/memory");
  await sleep(700);
  await rec.start("n04");
  await rec.scrollTo("#memmap", null, { gap: 140 });
  await rec.click("#mapfit", "Fit", { after: 300 });
  await soft(async () => { const el = await rec.findText("139 notes", { part: true, within: "#memmap, .memtop, main" }); await rec.ring(el, "139 notes, on shelves"); });
  await rec.cam(await rec.find("#memmap"), 1.2, { ms: 1500 });
  await sleep(700);
  await rec.unring();
  await rec.camReset(500);
  rec.mark("panel");
  await rec.goto(chat);
  await sleep(300);
  await rec.scrollTo("#sidepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 500 });
  const acc = await rec.findIn("#sidebody li", "Accounts", "input[type=checkbox]");
  await rec.ring(acc, "Only what I tick");
  await rec.cam(acc, 1.45, { ms: 900, dx: 120 });
  await sleep(1100);
  await rec.unring();
  rec.mark("secret");
  await soft(async () => { const chip = await rec.findText("5 secret", { within: "#sidebody" }); await rec.ring(chip, "Secret: never shared"); await rec.cam(chip, 1.6, { ms: 800, dx: 140 }); });
  await sleep(1900);
  await rec.stop();
}
