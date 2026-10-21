/* p03 to p06 in one go, because they are one story: hire with a hold, the floor fee, accept by carrying on, then "not helpful".
   Runs against the console started with --payments paypal-mock (a practice server that speaks the PayPal API). Cut into scenes by its marks. */
import { sleep } from "../recorder.mjs";

async function approve(rec, main, linger = 1500) {
  const link = await rec.find("#convo .msg.system a.btn", "approval page");
  const tab = await rec.newTab(() => rec.clickEl(link, { after: 300 }));
  await rec.switchTo(tab);                                                            // the payment page, in its own tab
  await sleep(linger);
  await rec.click("button", "Approve the hold", { after: 1500 });
  await sleep(1100);
  await tab.close();
  await rec.switchTo(main);                                                           // back to the chat, which carries on by itself
}

async function ask(rec, text) {
  await rec.click("#draft", null, { after: 300 });
  await rec.type(text, { delay: 38 });
  await sleep(400);
  await rec.click("#send", null, { after: 300 });
}

const answered = (n) => ({ fn: (n) => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= n, n });

export default async function (rec) {
  const main = rec.page;
  await rec.goto("/");
  await sleep(1000);
  await rec.start("pay");
  rec.mark("p03.start");
  await rec.click("a.stall.newstall", null, { after: 700 }).catch(() => {});             // with no chats yet the helpers are already on the page
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.click(".pick .btn.go2", "Chat", { nth: 1, after: 1500 });                // Private Analyst (40 cents)
  await rec.waitFor(() => location.pathname.startsWith("/chats/"));
  await sleep(700);
  await rec.scrollTo("#sidepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 800 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Accounts", "input[type=checkbox]"), { after: 1200 });
  await rec.scrollTo();
  await ask(rec, "Which accounts are at risk?");
  await rec.waitFor(() => document.querySelector("#convo .msg.system a.btn"), { timeout: 60000 });
  await sleep(900);
  rec.mark("approval");
  await approve(rec, main);                                                            // approve the hold on the payment page
  await rec.waitFor(() => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 1, { timeout: 120000 });
  rec.mark("p03.end");
  rec.mark("p04.start");
  await sleep(2200);
  await rec.click("#coinbtn", null, { after: 1500 });                                  // the coins chip: held, and the floor fee captured
  await sleep(3200);
  await rec.click("#wallet [data-close]", "Close", { after: 800 });
  rec.mark("p04.end");
  rec.mark("p05.start");
  await ask(rec, "And which one is the biggest?");                                     // carrying on means the last answer was good enough
  await rec.waitFor(() => document.querySelector("#convo .msg.system a.btn"), { timeout: 60000 });
  await sleep(500);
  await approve(rec, main, 900);
  await rec.waitFor(() => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 2, { timeout: 120000 });
  await sleep(1500);
  await rec.click("#coinbtn", null, { after: 1500 });                                  // receipts: the first answer is paid, the author is paid less the fee
  await rec.scrollTo("#walletbody .receipt", null, { block: "start", gap: 40 }).catch(() => {});
  await sleep(3800);
  await rec.click("#wallet [data-close]", "Close", { after: 800 });
  rec.mark("p05.end");
  rec.mark("p06.start");
  await rec.click("#convo button.linkbtn", "Not helpful", { after: 1500 });            // not helpful: deposit only
  await sleep(1200);
  await rec.click("#coinbtn", null, { after: 1500 });
  await sleep(3800);
  rec.mark("p06.end");
  await rec.stop();
}
