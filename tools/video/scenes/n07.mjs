/* n07: Memory only by consent. A helper suggests a fact; nothing is saved until the person says yes; then it can be taken back. */
import { readFile } from "node:fs/promises";
import { sleep } from "../recorder.mjs";

const QUESTIONS = ["What is the single most important thing to remember about Acme?", "Which contact at Globex matters most?", "What should I remember about Hooli?", "Who owns the security questionnaire?"];

async function ensureSuggestion(rec) {
  const chat = new URL(JSON.parse(await readFile("../../video-out/n05.chat.json", "utf8")).url).pathname.split("/").pop();
  for (const q of QUESTIONS) {
    const n = await rec.page.evaluate(async () => (await (await fetch("/api/state")).json()).proposals.length);
    if (n > 0) return;
    await rec.page.evaluate(async (id, text) => {
      const token = document.body.dataset.token;
      await fetch("/api/thread/send", { method: "POST", headers: { "X-Bridge-Token": token, "Content-Type": "application/json" }, body: JSON.stringify({ id, text }) });
    }, chat, q);
  }
  const n = await rec.page.evaluate(async () => (await (await fetch("/api/state")).json()).proposals.length);
  if (!n) throw new Error("no helper suggested anything to remember; try again");
}

export default async function (rec) {
  await rec.goto("/");
  await ensureSuggestion(rec);
  await rec.goto("/");
  await sleep(1200);
  await rec.start("n07");
  await sleep(700);
  await rec.scrollTo("#notespanel", null, { gap: 120 });                              // "Helpers suggest you remember": nothing saved yet
  await rec.hover("#notes .note", null, { ms: 700 });
  await sleep(1800);
  rec.mark("yes");
  await rec.click("#notes .note .btn", "Remember it", { after: 1500 });                // the person says yes
  await rec.scrollTo();
  await rec.click("nav.tabs a", "My memory", { after: 1200 });
  await rec.scrollTo("#memmap", null, { gap: 150 });
  await rec.click("#mapfit", "Fit", { after: 800 });
  await rec.click("#memmap .mnode", "From Helpers", { after: 1800 });                  // the shelf where suggestions land
  rec.mark("undo");
  await rec.click("#memlist .mem .btn", "Undo what that answer added", { after: 2200 }); // and it can be taken back
  await sleep(1200);
  await rec.stop();
}
