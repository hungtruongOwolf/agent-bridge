import { sleep } from "../recorder.mjs";
export default async function (rec) {
  await rec.goto("/");
  await sleep(800);
  await rec.start("look");
  await rec.click("a.stall.newstall", null, { after: 700 });
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.click(".pick .btn.go2", "Chat", { nth: 2, after: 1200 });
  await rec.waitFor(() => location.pathname.startsWith("/chats/"));
  await sleep(800);
  await rec.shot("chat0");
  await rec.scrollTo("#sidepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 700 });
  await rec.shot("chat1");
  console.log(await rec.page.evaluate(() => [...document.querySelectorAll("#sidebody li")].map((l) => l.textContent.trim().replace(/\s+/g, " ").slice(0, 60)).join(" | ")));
  console.log("page", await rec.page.evaluate(() => location.pathname + " h=" + document.documentElement.scrollHeight));
  await rec.stop();
}
