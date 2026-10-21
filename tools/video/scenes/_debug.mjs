import { sleep } from "../recorder.mjs";
export default async function (rec) {
  await rec.goto("/chats/t_2a35d60a"); await sleep(2000);
  console.log(await rec.page.evaluate(() => [...document.querySelectorAll("#convo details")].map((d) => [d.className, d.textContent.slice(0, 40), d.getBoundingClientRect().height])));
  await rec.shot("dbg2");
}
