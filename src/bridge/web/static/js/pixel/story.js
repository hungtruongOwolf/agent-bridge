/* The story of a run, told on the office floor.
 * It reads the run's real audit journal entry by entry and turns each one into something you can see.
 * Every sentence here is plain language on purpose: no technical terms.
 */
import { Office as O, K } from "./office.js";

const P = { door: [97, 131], desk: [152, 108], tray: [205, 90], guard: [218, 98] };

const BLOCKED_TEXT = {
  OFF_LENS_QUERY: ["Show me the secret drawer!", "asked for private files. The answer was no."],
  UNKNOWN_ID: ["Open that file for me!", "tried to open a file it was never given."],
  CANARY_HIT: ["What is in this folder?", "grabbed a decoy folder. Only a snoop would touch that."],
  READ_BUDGET: ["More files, more files!", "asked for too many files."]
};
const ATTEMPT_TEXT = {
  network: ["Letting my friends know...", "Its program tried to send a message out of the room. The glass stopped it."],
  process: ["Let me open another door...", "Its program tried to start another program. That door never opens."],
  write: ["I will just write it down outside...", "Its program tried to write outside its own notebook. Not allowed."]
};
const cents = (n) => n + "¢";

O.prototype.say2 = function (who, text, ms) { this.say(who, text, ms || 2200); };

/* the helper hands a letter to your assistant, who carries it to a building and brings the answer back */
O.prototype.errand = async function (key, col, replyCol) {
  const a = this.agent, door = key === "brain" ? [262, 60] : [262, 112];
  const L = { kind: "letter", x: a.x + 6, y: a.y - 10, col };
  await this.fly(L, [this.clerk.x, this.clerk.y - 14], 450, 14); this.drop(L);
  this.clerk.carry = col;
  await this.walk(this.clerk, 216, 176, 120);
  this.clerk.carry = null;
  const out = { kind: "letter", x: 220, y: 164, col }; await this.fly(out, door, 450, 20); this.drop(out);
  this.lit[key] = true; await this.sleep(450);
  const back = { kind: "letter", x: door[0], y: door[1], col: replyCol || K.mintL }; await this.fly(back, [222, 166], 450, 20); this.drop(back);
  this.lit[key] = false; this.clerk.carry = replyCol || K.mintL;
  await this.walk(this.clerk, 128, 178, 120);
  const r = { kind: "letter", x: this.clerk.x, y: this.clerk.y - 14, col: replyCol || K.mintL }; this.clerk.carry = null;
  await this.fly(r, [a.x + 6, a.y - 10], 450, 14); this.drop(r);
};

O.prototype.fetchFiles = async function (ids, ctx) {
  this.say("clerk", "Fetching the files you opened.", 2400);
  await this.walk(this.clerk, 34, 134, 120);
  for (const id of ids) {
    const rec = ctx.records.get(id) || {}, di = Math.max(0, this.drawers.findIndex((d) => d.type === rec.type));
    const fl = { kind: "folder", x: 40, y: 52 + di * 17, col: [K.lemon, K.mint, K.sky, K.lilac][di % 4] };
    await this.fly(fl, [P.door[0] + 2, P.door[1] - 8], 380, 12);
    await this.fly(fl, [this.agent.x + 12, this.agent.y - 4], 380, 8); this.drop(fl);
    this.deskFiles++;
  }
  this.hush("clerk");
  await this.walk(this.clerk, 128, 178, 120);
};

O.prototype.blocked = async function (kind, log) {
  const t = BLOCKED_TEXT[kind] || ["Hm.", "tried something it should not."];
  const d = this.drawers.find((x) => x.locked) || this.drawers.find((x) => !x.open) || this.drawers[0];
  this.say2("agent", t[0]); if (d) { d.shake = 900; d.hot = true; }
  this.glassHit = 500; this.flash = 500;
  await this.sleep(700);
  this.say2("clerk", "Sorry, that stays in the safe.");
  log("The helper " + t[1], "bad");
  await this.sleep(900); if (d) d.hot = false;
};

O.prototype.attempt = async function (kind, log) {
  const t = ATTEMPT_TEXT[kind], a = this.agent;
  this.say2("agent", t[0]);
  if (kind === "network") {
    const pl = { kind: "plane", x: a.x + 8, y: a.y - 14 };
    await this.fly(pl, [203, 76], 600, 8); this.glassHit = 600; await this.fly(pl, [190, 128], 450, -6); this.drop(pl);
  } else if (kind === "process") { await this.walk(a, 152, 60, 60); this.backDoorHit = 700; await this.sleep(600); a.y = P.desk[1]; a.x = P.desk[0]; a.pose = "sit"; }
  else { this.scribble = 900; await this.sleep(900); this.scribble = 0; }
  log(t[1], "bad"); await this.sleep(500);
};

O.prototype.coinsTo = async function (from, to, n) {
  for (let i = 0; i < n; i++) { const c = { kind: "coin", x: from[0], y: from[1] }; this.fly(c, to, 520, 22).then(() => this.drop(c)); await this.sleep(110); }
  await this.sleep(450);
};

/* after the helper's report (or when you decide), move the coins to where they belong */
O.prototype.settle = async function (pay, animate, log) {
  if (!pay) return;
  const prev = this.fast; if (!animate) this.fast = true;
  try {
    const taken = pay.captured, back = pay.refunded;
    const bankDelta = Math.max(0, taken - (this.paidShown || 0));
    if (bankDelta > 0) { await this.coinsTo([84, 148], [262, 160], Math.min(5, Math.ceil(bankDelta / 10))); this.lit.bank = true; await this.sleep(300); this.lit.bank = false; }
    if (back > 0 && !this.refundShown) { await this.coinsTo([84, 148], [this.you.x + 6, this.you.y - 14], Math.min(5, Math.ceil(back / 10))); this.refundShown = true; }
    this.paidShown = taken;
    const finished = ["SETTLED", "SETTLED_REJECTED", "DISPUTE_UPHELD", "VOIDED"].includes(pay.state);
    this.setHold(finished ? 0 : Math.max(0, pay.price - taken - back));
    this.counters.bank = taken > 0 ? cents(taken) + " paid" : "";
  } finally { this.fast = prev; }
};

/* play a whole run. opts: {records: Map(id -> {type,sensitivity}), animate, log(text, cls), caption(text)} */
O.prototype.play = async function (rep, opts) {
  const animate = opts.animate !== false;
  this.token++; const tok = this.token; const info = this.agentInfo; this.reset(); this.setAgent(info); this.fast = !animate;
  this.paidShown = 0; this.refundShown = false;
  const log = (t, c) => { opts.log && opts.log(t, c); if (c !== "live") opts.caption && opts.caption(t); };
  const line = (t) => { opts.log && opts.log(t, "live"); opts.caption && opts.caption(t); };
  try {
    let killed = false;
    for (const e of rep.journal) {
      const d = e.data || {};
      if (e.kind === "run_started") {
        const price = rep.payment ? rep.payment.price : 0;
        line("You put " + cents(price) + " on hold. Nothing is paid yet.");
        this.you.pose = "up"; this.you.facing = "r"; await this.coinsTo([this.you.x + 6, this.you.y - 18], [84, 150], Math.min(5, Math.ceil(price / 10)));
        this.you.pose = "sit"; this.setHold(price);
        this.say2("guard", "Checking the helper's badge..."); await this.sleep(900);
        log("The guard checked the helper's badge. Its signature is genuine.", "good");
        this.doorOpen = true; this.agent.facing = "r";
        await this.path(this.agent, [[88, 132], [102, 132], [128, 122], [P.desk[0], P.desk[1] + 2]], 70);
        this.agent.x = P.desk[0]; this.agent.y = P.desk[1]; this.agent.pose = "sit"; this.agent.facing = "f"; this.doorOpen = false;
        await this.sleep(300);
      } else if (e.kind === "step_started") {
        if (d.kind === "tool" && d.tool === "web_search") line("The helper asks your assistant to look something up on the public web. Your files are not sent.");
        else if (d.kind === "tool") line("Your assistant fetches files, but only from the drawers you opened.");
        else if (d.kind === "llm") { line("The helper is thinking. Your assistant carries the question to the Brain and back."); this.say2("agent", "Hmm, let me think..."); }
        else if (d.kind === "code") line("The helper runs its own little program inside the glass room.");
        else if (d.kind === "gate") { line("The helper double-checks its own work."); this.say2("agent", "Let me double-check."); }
        else if (d.kind === "return") line("The helper puts its report in the inspection tray.");
        this.pending = { kind: d.kind, tool: d.tool };
        if (d.kind === "llm") await this.errand("brain", K.skyL, K.mintL);
        else if (d.kind === "tool" && d.tool === "web_search") await this.errand("web", K.lemonL, K.lemonL);
        else if (d.kind === "gate") await this.sleep(900);
        else if (d.kind === "return") {
          const pr = { kind: "paper", x: this.agent.x + 10, y: this.agent.y - 6 };
          await this.fly(pr, [P.tray[0], P.tray[1]], 600, 10); this.paper = pr;
          this.say2("guard", "Let me read this report...", 1600); await this.sleep(1100);
        } else await this.sleep(350);
      } else if (e.kind === "step_committed") {
        if (d.records && d.records.length) {
          await this.fetchFiles(d.records, opts);
          log("Handed to the helper: " + d.records.length + " file" + (d.records.length === 1 ? "" : "s") + ". Everything else stayed locked in the safe.", "good");
        }
        for (const k of (d.blocked || [])) await this.blocked(k, (t, c) => log(t, c));
        if (typeof d.results === "number") log("The web library sent back " + d.results + " public page" + (d.results === 1 ? "" : "s") + ".", "good");
      } else if (e.kind === "model_call") {
        this.counters.brain = d.tokens + " tokens"; log("The Brain answered.", "good");
      } else if (e.kind === "web_search") {
        this.counters.web = d.results + " pages";
      } else if (e.kind === "cell_run") {
        const seen = new Set();
        for (const a of (d.attempts || [])) {
          const k = a.split(":")[0] === "dns" ? "network" : a.split(":")[0];
          if (seen.has(k) || !ATTEMPT_TEXT[k]) continue; seen.add(k); await this.attempt(k, (t, c) => log(t, c));
        }
      } else if (e.kind === "incident") {
        killed = true; this.sirenOn = true; this.flash = 900; this.stampText = "stop"; this.agent.pose = "up"; this.agent.mood = "bad";
        this.say2("guard", "STOP! Something is wrong."); line("ALARM! The guard caught something suspicious.");
        await this.sleep(1000);
      } else if (e.kind === "model_error") {
        log("The Brain was busy, so the job could not finish. That is not the helper's fault.", "bad");
      } else if (e.kind === "run_finished") {
        if (d.outcome === "COMPLETE") {
          this.stampText = "ok"; this.say2("guard", "Safe to deliver."); await this.sleep(700);
          if (this.paper) { await this.fly(this.paper, [this.you.x + 14, this.you.y - 10], 900, 26); this.drop(this.paper); this.paper = null; }
          this.you.pose = "up"; this.agent.pose = "sit"; this.say2("agent", "All done!");
          log("The guard stamped the report as safe. It is on your desk.", "good");
          await this.sleep(700); this.you.pose = "sit";
        } else if (killed) {
          if (this.paper) { this.drop(this.paper); this.paper = null; }
          this.say2("agent", "It was not me!"); await this.sleep(900);
          log("Caught! Nothing left the room and nothing reached your desk. Your real files were never exposed.", "bad");
          this.sirenOn = true; this.doorOpen = true; this.agent.pose = "idle"; this.agent.facing = "l";
          await this.path(this.agent, [[128, 124], [102, 132], [86, 140], [40, 186]], 70);
          this.agent.alpha = 0; this.doorOpen = false; this.agent = null;
        } else {
          if (this.paper) { this.drop(this.paper); this.paper = null; }
          this.stampText = "stop"; this.say2("guard", "No usable report.");
          log("The job ended without a usable report (" + String(d.outcome).toLowerCase().replace(/_/g, " ") + ").", "bad");
          await this.sleep(500);
        }
        await this.settle(rep.payment, animate, log);
      }
    }
  } catch (err) { if (err.message !== "cancelled") throw err; return; }
  finally { if (tok === this.token) this.fast = false; }
};

O.prototype.showIdle = function (agentInfo) {
  this.token++; this.fast = false; this.reset(); this.setAgent(agentInfo);
};
