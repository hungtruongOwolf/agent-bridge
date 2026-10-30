/* p03 to p05 in one go (version 2), because they are one story: hire with a hold of 40 cents, the real price of 25, accept, then "not helpful".
   Runs against the console started with --payments paypal-mock (a practice server that speaks the PayPal API), with the helper Account Brief
   (10 cents light, 25 standard, 40 deep) reading three files of Work > Accounts > Initech. Cut into scenes by its marks. */
import { sleep } from "../recorder.mjs";

const soft = async (f) => { try { await f(); } catch (e) { console.error("skipped:", e.message); } };

async function approve(rec, main, linger = 1800, tag = "") {
  const link = await rec.find("#convo .msg.system a.btn", "approval page");
  const tab = await rec.newTab(() => rec.clickEl(link, { after: 300 }));
  await rec.switchTo(tab);                                                            // the payment page, in its own tab
  rec.mark("tab" + tag);
  await sleep(linger);
  await rec.page.screenshot({ path: "../../video-out/shot-pay-approval.png" });
  await rec.click("button", "Approve the hold", { after: 1500 });
  await sleep(1100);
  await tab.close();
  await rec.switchTo(main);                                                           // back to the chat, which carries on by itself
  rec.mark("back" + tag);
}

async function ask(rec, text) {
  await rec.click("#draft", null, { after: 300 });
  await rec.type(text, { delay: 38 });
  await sleep(400);
  await rec.click("#send", null, { after: 300 });
}

export default async function (rec) {
  const main = rec.page;
  await rec.goto("/");
  await sleep(900);
  // set-up that is not part of the picture: a new chat with Account Brief and the Initech shelf ticked
  await rec.click("a.stall.newstall", null, { after: 700 }).catch(() => {});
  await rec.scrollTo("#hirepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn(".pick", "Account Brief", ".btn.go2"), { after: 1200 });
  await rec.waitFor(() => location.pathname.startsWith("/chats/"));
  await sleep(600);
  await rec.scrollTo("#sidepanel", null, { gap: 100 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 500 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Accounts", ".twist"), { after: 500 });
  await rec.clickEl(await rec.findIn("#sidebody li", "Initech", "input[type=checkbox]"), { after: 700 });
  await rec.scrollTo();
  await sleep(500);
  await rec.start("pay");
  rec.mark("p03.start");
  await sleep(900);
  await ask(rec, "Which accounts are at risk?");
  rec.mark("ask1");
  await rec.waitFor(() => document.querySelector("#convo .msg.system a.btn"), { timeout: 60000 });
  await sleep(500);
  await soft(async () => { const card = await rec.find("#convo .msg.system"); await rec.ring(card, "Hold of 40¢: the most it can charge"); await rec.cam(card, 1.3, { ms: 900 }); });
  await sleep(3600);
  await rec.unring();
  await rec.camReset(500);
  rec.mark("card1");
  await approve(rec, main, 6200, "1");                                                 // approve the hold on the payment page
  await soft(async () => { await rec.ring(await rec.find("#coinbtn"), "Held, nothing taken yet"); });
  await sleep(3600);
  await rec.unring();
  rec.mark("p03.end");
  rec.mark("p04.start");
  await rec.waitFor(() => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 1, { timeout: 120000 });
  rec.mark("answer1");
  await sleep(4200);
  await rec.page.screenshot({ path: "../../video-out/shot-pay-answer.png" });
  await rec.click("#coinbtn", null, { after: 1500 });                                  // the coins chip: held, and the real price
  await soft(async () => { await rec.clickEl(await rec.findText("What happened", { within: "#wallet" }), { after: 700 }); });
  await soft(async () => { const l = await rec.findText("of the 40¢ hold", { part: true, within: "#wallet" }); await rec.ring(l, "Priced by what the run did"); });
  await rec.page.screenshot({ path: "../../video-out/shot-pay-wallet1.png" });
  await sleep(8200);
  await rec.unring();
  await rec.click("#wallet [data-close]", "Close", { after: 1200 });
  rec.mark("p04.end");
  rec.mark("p05.start");
  await ask(rec, "And which one is the biggest?");                                     // carrying on means the last answer was good enough: accepted
  rec.mark("ask2");
  await rec.waitFor(() => document.querySelector("#convo .msg.system a.btn"), { timeout: 60000 });
  await sleep(500);
  await approve(rec, main, 900, "2");
  await rec.waitFor(() => document.querySelectorAll("#convo .msg.helper:not(.thinking)").length >= 2, { timeout: 120000 });
  rec.mark("answer2");
  await sleep(1300);
  await rec.click("#coinbtn", null, { after: 1500 });                                  // receipts: the first answer is paid, the author is paid
  await soft(async () => { await rec.scrollTo("#walletbody .receipt", null, { block: "start", gap: 40 }); });
  await rec.page.screenshot({ path: "../../video-out/shot-pay-wallet2.png" });
  await soft(async () => { const l = await rec.findText("Paid", { within: "#walletbody" }); await rec.ring(l, "Accepted: the author is paid"); });
  await sleep(3400);
  await rec.unring();
  await rec.click("#wallet [data-close]", "Close", { after: 800 });
  rec.mark("nothelp");
  await rec.click("#convo button.linkbtn", "Not helpful", { after: 1500 });            // not helpful: only the fee
  await sleep(1000);
  await rec.click("#coinbtn", null, { after: 1500 });
  await soft(async () => { await rec.clickEl(await rec.findText("What happened", { within: "#wallet" }), { after: 700 }); });
  await soft(async () => { const l = await rec.findText("deposit only", { part: true, within: "#wallet" }); await rec.ring(l, "Only the small fee is kept"); });
  await rec.page.screenshot({ path: "../../video-out/shot-pay-wallet3.png" });
  await sleep(3400);
  rec.mark("p05.end");
  await rec.stop();
}
