/* p07 (version 2): how authors charge. The Publish tab of a helper, each plan card in turn with its worked price example, then the wallet with a monthly plan. About 23 seconds. */
import { sleep } from "../recorder.mjs";

const soft = async (f) => { try { await f(); } catch (e) { console.error("skipped:", e.message); } };

export default async function (rec) {
  await rec.goto("/helpers/idea-sorter/publish");
  await sleep(1400);
  await rec.start("p07");
  await sleep(500);
  for (const [name, label] of [["One price", "One flat price"], ["By files read", "Follows the files it reads"], ["By thinking used", "Follows the thinking used"], ["By how hard", "Light, standard or deep"]]) {
    await soft(async () => {
      const card = await rec.find(".plancard", name);
      await rec.clickEl(card, { after: 500 });
      await rec.ring(card, label);
      await rec.cam(card, 1.3, { ms: 700, dy: -30 });
    });
    await sleep(1450);
    await rec.unring();
  }
  await rec.page.screenshot({ path: "../../video-out/shot-p07-complexity.png" });
  await soft(async () => {
    const card = await rec.find(".plancard", "Monthly plan");
    await rec.clickEl(card, { after: 500 });
    await rec.ring(card, "A set number of answers. No auto-renew.");
    await rec.cam(card, 1.3, { ms: 700, dy: -30 });
  });
  await sleep(2600);
  await rec.unring();
  await rec.camReset(600);
  await soft(async () => { await rec.click("#coinbtn", null, { after: 1200 }); });
  await soft(async () => { const l = await rec.findText("answers", { part: true, within: "#wallet" }); await rec.ring(l, "Answers left in the plan"); });
  await rec.page.screenshot({ path: "../../video-out/shot-p07-wallet.png" });
  await sleep(2600);
  await rec.stop();
}
