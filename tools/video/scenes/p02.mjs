/* p02: the product in one breath: the market floor with its stalls, the market square, and the coins chip. */
import { sleep } from "../recorder.mjs";

export default async function (rec) {
  await rec.goto("/");
  await sleep(1000);
  await rec.start("p02");
  await sleep(900);
  await rec.hover("a.stall", "Weekly account review", { ms: 900 });
  await sleep(900);
  await rec.hover(".sqcard", "Guard post", { ms: 800 });
  await sleep(700);
  await rec.hover(".sqcard", "Bank", { ms: 700 });
  await sleep(700);
  await rec.hover(".sqcard", "Library", { ms: 700 });
  await sleep(700);
  await rec.hover("#coinbtn", null, { ms: 900 });
  await sleep(1400);
  await rec.stop();
}
