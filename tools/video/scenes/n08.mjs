/* n08 (version 2): sell a setup. The step graph, a step dragged, the plain-words checks, then Publish with the plan cards and the price preview. About 18 seconds. */
import { sleep } from "../recorder.mjs";

const soft = async (f) => { try { await f(); } catch (e) { console.error("skipped:", e.message); } };

export default async function (rec) {
  await rec.goto("/helpers/client-pulse");
  await sleep(1300);
  await rec.start("n08");
  await sleep(500);
  const graph = await rec.find("#graph");
  await rec.cam(graph, 1.25, { ms: 1300 });
  await soft(async () => { await rec.click("button", "Tidy up", { after: 900 }); });                  // the steps arrange themselves
  await rec.page.screenshot({ path: "../../video-out/shot-n08-graph.png" });
  await soft(async () => { const chk = await rec.findText("never be connected to the web", { part: true, within: "main, body" }); await rec.ring(chk, "The checker enforces it"); await rec.cam(chk, 1.45, { ms: 900, dx: -60 }); });
  await sleep(2300);
  await rec.unring();
  await rec.camReset(600);
  rec.mark("publish");
  await rec.click("#ptab-publish", null, { after: 1000 });
  await soft(async () => { await rec.click(".plancard", "By how hard", { after: 900 }); });
  await soft(async () => { const card = await rec.find(".plancard", "By how hard"); await rec.ring(card, "Set a price"); await rec.cam(card, 1.35, { ms: 900, dy: -40 }); });
  await sleep(2200);
  await rec.page.screenshot({ path: "../../video-out/shot-n08-publish.png" });
  await rec.unring();
  await rec.camReset(500);
  await rec.stop();
}
