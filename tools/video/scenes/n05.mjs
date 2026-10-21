/* n05: Ask and answer. Start a chat with Deal Brief, open the Work > Accounts shelf, ask, watch the little office, read where the answer came from.
   The answer is made live by Nemotron on Nebius, so the wait is real; the edit shortens it. */
import { writeFile } from "node:fs/promises";
import { sleep } from "../recorder.mjs";

export default async function (rec) {
  await rec.goto("/");
  await sleep(1000);
  await rec.start("n05");
  await rec.click("a.stall.newstall", null, { after: 1000 });
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.click(".pick .btn.go2", "Chat", { nth: 2, after: 1500 });                // Deal Brief (third in the list)
  await rec.waitFor(() => location.pathname.startsWith("/chats/"));
  await sleep(900);
  rec.mark("tick");
  await rec.scrollTo("#sidepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 900 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Accounts", "input[type=checkbox]"), { after: 1400 });   // the helper may see Work > Accounts, nothing else
  await rec.scrollTo();
  await rec.click("#draft", null, { after: 400 });
  await rec.type("Which accounts need attention first?", { delay: 38 });
  await sleep(500);
  rec.mark("send");
  await rec.click("#send", null, { after: 300 });
  await rec.waitFor(() => document.querySelectorAll("#convo .msg.helper:not(.thinking), #convo .msg.system").length >= 1, { timeout: 120000 });
  rec.mark("answer");
  await sleep(2200);
  await rec.click("#convo details.based summary", "Written from", { after: 1800 });  // which of my files it used
  await rec.click("#convo details.based summary", "How this answer was made", { after: 2800 });
  rec.mark("how");
  await writeFile("../../video-out/n05.chat.json", JSON.stringify({ url: rec.page.url() }));
  await rec.stop();
}
