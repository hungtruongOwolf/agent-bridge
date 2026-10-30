import { sleep } from "../recorder.mjs";
export default async function (rec) {
  await rec.goto("/memory");
  await sleep(800);
  await rec.start("camtest");
  const tgt = await rec.find(".memtop, h2", null);
  await rec.cam(tgt, 1.8, { ms: 700 });
  await sleep(300);
  await rec.shot("cam1");
  const btn = await rec.find("button", "Add to memory");
  await rec.ring(btn, "Add to memory");
  await sleep(300);
  await rec.shot("cam1b");
  await rec.camReset(500);
  await sleep(300);
  await rec.shot("cam2");
  await rec.stop();
}
