/* p07: five ways to charge. The Publish tab of a helper, each plan card in turn, with its worked price example. */
import { sleep } from "../recorder.mjs";

export default async function (rec) {
  await rec.goto("/helpers/idea-sorter/publish");
  await sleep(1500);
  await rec.start("p07");
  await sleep(900);
  for (const name of ["By files read", "By thinking used", "By how hard the question was", "Monthly plan", "One price"]) {
    await rec.click(".plancard", name, { after: 1500 });
  }
  await sleep(900);
  await rec.stop();
}
