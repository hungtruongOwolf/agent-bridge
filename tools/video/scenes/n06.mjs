/* n06 (version 2): telling good from bad. The helpers for hire with their trust, one helper's page with what the certifier measured (and its other versions), and the helpers caught cheating. */
import { sleep } from "../recorder.mjs";

const soft = async (f) => { try { await f(); } catch (e) { console.error("skipped:", e.message); } };

export default async function (rec) {
  await rec.goto("/");
  await sleep(900);
  await rec.start("n06");
  await rec.click("a.stall.newstall", null, { after: 700 });
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.hover(".pick", "Action Finder", { ms: 700 });
  await soft(async () => { await rec.ring(await rec.find(".pick", "Action Finder"), "Tested on the same questions"); });
  await sleep(1200);
  await rec.unring();
  rec.mark("meet");
  await rec.clickEl(await rec.findIn(".pick", "Action Finder", "a.btn"), { after: 1800 });
  await rec.page.screenshot({ path: "../../video-out/shot-n06-profile.png" });
  const dlg = await rec.find("#profile");
  const b = await dlg.boundingBox();
  await soft(async () => { const m = await rec.findText("Passed 14 of 16", { part: true, within: "#profile" }); await rec.ring(m, "Right answers, same test"); });
  await sleep(1500);
  await rec.unring();
  await rec.wheel(b.x + b.width / 2, b.y + b.height / 2, 560, 5, 120);
  await sleep(1400);
  rec.mark("versions");
  await rec.page.screenshot({ path: "../../video-out/shot-n06-profile2.png" });
  await rec.click("#profile [data-close]", "Close", { after: 600 });
  await rec.scrollTo("#picker .small.muted", "caught cheating", { block: "center" });
  await soft(async () => { await rec.ring(await rec.find("#picker .small", "caught cheating"), "Flagged for everyone"); });
  await sleep(2400);
  await rec.stop();
}
