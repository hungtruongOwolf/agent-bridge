/* n03: My memory. The map, a shelf opened, the tick panel of a chat, and the red rings of the secret shelves. */
import { sleep } from "../recorder.mjs";

export default async function (rec) {
  await rec.goto("/memory");
  await sleep(1200);
  await rec.start("n03");
  await sleep(1300);
  await rec.scrollTo("#memmap", null, { gap: 150 });                              // the map fills the screen
  await rec.click("#mapfit", "Fit", { after: 1200 });
  rec.mark("shelves");
  await rec.click("#memmap .mnode", "Work", { after: 1500 });                     // open Work: its shelves grow out of it
  await rec.click("#memmap .mnode", "Accounts", { after: 2000 });                 // the notes of Accounts fill the list
  rec.mark("chat");
  await rec.scrollTo();
  await rec.click("nav.tabs a", "My office", { after: 1200 });
  await rec.click("a.stall", "Weekly account review", { after: 1800 });
  await rec.scrollTo("#sidepanel", null, { gap: 100 });                           // what the helper may see
  await sleep(600);
  await rec.clickEl(await rec.findIn("#sidebody li", "Work", ".twist"), { after: 1600 });   // open Work: only Accounts is ticked
  await sleep(1600);
  rec.mark("rings");
  await rec.scrollTo();
  await rec.click("nav.tabs a", "My memory", { after: 1400 });
  await rec.scrollTo("#memmap", null, { gap: 150 });
  await rec.click("#mapfit", "Fit", { after: 900 });
  await rec.hover("#memmap .mnode", "Money", { ms: 900 });                        // the red ring: secret notes on this shelf
  await sleep(1700);
  await rec.hover("#memmap .mnode", "Personal", { ms: 800 });
  await sleep(1800);
  await rec.stop();
}
