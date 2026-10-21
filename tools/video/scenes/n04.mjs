/* n04: Trust by evidence. The list of helpers with their trust, price and test line; one helper's page; the ones flagged for cheating. */
import { sleep } from "../recorder.mjs";

export default async function (rec) {
  await rec.goto("/");
  await sleep(1200);
  await rec.start("n04");
  await sleep(900);
  await rec.click("a.stall.newstall", null, { after: 1200 });                       // Open a new stall: the helpers for hire
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.hover(".pick", "Deal Brief", { ms: 800 });
  await sleep(1400);
  await rec.hover(".pick", "Quick Skim", { ms: 800 });
  await sleep(1200);
  rec.mark("meet");
  await rec.click(".pick a.btn", "Meet", { nth: 0, after: 2200 });                  // the profile: what it does and its test results
  const dlg = await rec.find("#profile");
  const b = await dlg.boundingBox();
  await rec.wheel(b.x + b.width / 2, b.y + b.height / 2, 520, 5, 140);
  await sleep(1500);
  rec.mark("flagged");
  await rec.click("#profile [data-close]", "Close", { after: 900 });
  await rec.scrollTo("#picker .small.muted", "caught cheating", { block: "center" }); // helpers caught cheating in tests
  await rec.hover("#picker .small", "caught cheating", { ms: 700 });
  await sleep(2200);
  await rec.stop();
}
