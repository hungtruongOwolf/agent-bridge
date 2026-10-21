/* n08: Build your own. The step graph, a step dragged, a practice run on chosen shelves with the graph lighting up along the real path, then Publish. */
import { sleep } from "../recorder.mjs";

export default async function (rec) {
  await rec.goto("/helpers/client-pulse");
  await sleep(1500);
  await rec.start("n08");
  await sleep(900);
  const node = await rec.find("#graph .node", "Think");                               // drag a step to a new place
  const p = await rec.center(node);
  await rec.glide(p.x, p.y, 700);
  await rec.page.mouse.down();
  await rec.glide(p.x + 70, p.y - 50, 600);
  await rec.page.mouse.up();
  await sleep(900);
  rec.mark("practise");
  await rec.click("#ptab-try", null, { after: 900 });                                 // Practise
  await rec.click("#panelbody textarea", null, { after: 300 });
  await rec.type("Where does each client stand?", { delay: 38 });
  await rec.clickEl(await rec.findIn("#panelbody label", "Work", "input"), { after: 500 });   // the shelves it may open
  rec.mark("run");
  await rec.click("#panelbody .btn", "Run it", { after: 300 });
  await rec.waitFor(() => document.querySelector("#panelbody .tryout .report, #panelbody .tryout .okline, #panelbody .tryout .report") !== null || (document.querySelector(".tryout") && document.querySelector(".tryout").textContent.length > 40 && !/Running/.test(document.querySelector(".tryout").textContent)), { timeout: 120000 });
  await sleep(3200);                                                                  // the graph pulses along the path it took
  rec.mark("publish");
  await rec.click("#ptab-publish", null, { after: 1600 });                            // Publish: price and tests
  await sleep(1800);
  await rec.stop();
}
