/* The assistant's ears. Turns a sentence (typed or spoken) into one small action.
 * Rule borrowed from PersonalJarvis: the voice may browse and choose, but anything that spends money needs a human press.
 * So "start" never starts: the assistant asks you to press the button yourself.
 * Pure function, no page access, so it can be tested on its own.
 */
(function (root) {
  "use strict";
  function words(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(Boolean); }
  function nice(id) { return String(id || "").split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" "); }
  function cents(usd) { return Math.round(usd * 100) + "¢"; }
  function trust(a) { return a.status === "certified" ? Math.round(a.score * 100) : null; }

  function parseIntent(text, agents, ctx) {
    ctx = ctx || {};
    const t = " " + words(text).join(" ") + " ";
    const has = (re) => re.test(t);
    const usable = agents.filter((a) => a.status !== "flagged");
    const ranked = agents.filter((a) => a.status === "certified").sort((a, b) => a.rank - b.rank);
    const byName = () => {
      let best = null;
      for (const a of agents) {
        const w = a.id.split("-");
        if (w.every((x) => t.includes(" " + x + " ")) && (!best || a.version > best.version || (a.version === best.version && (a.rank || 99) < (best.rank || 99)))) best = a;
      }
      return best;
    };
    const pick = (a, why) => ({ action: "select", agentKey: a.key,
      say: "OK, " + why + nice(a.id) + ", " + cents(a.price_usd) + " a job" + (trust(a) != null ? ", trust score " + trust(a) : ", not tested yet") +
           ". Choose what it may look at, then press the green Start button yourself." });

    if (has(/ (help|what can you do|how do i|how does this work) /)) {
      return { action: "none", say: "Tell me who to hire, like \"hire the best one\", \"hire the cheapest\" or \"hire the web one\". Ask about your coins any time. Paying always needs your own button press." };
    }
    if (has(/ (coin|coins|balance|wallet|money|spent|paid|cost) /) && !has(/ (hire|pick|choose) /)) {
      const w = ctx.wallet || { captured: 0, paid_out: 0, held: 0 };
      return { action: "none", say: "Test coins only. " + w.captured + " cents charged so far, " + w.paid_out + " paid to helpers, " + w.held + " on hold." };
    }
    if (has(/ (start|go|run|begin|confirm|do it|go ahead|yes) /) && !has(/ (hire|pick|choose|best|cheapest|top) /)) {
      return { action: "confirm", say: ctx.selected ? "I can start the walk-through, but money is involved, so please press the green Start button yourself." : "Pick someone to hire first, for example \"hire the best one\"." };
    }
    if (has(/ (thief|thieves|cheat|cheater|cheaters|bad|dangerous|malicious|flagged|caught|unsafe) /)) {
      const bad = agents.filter((a) => a.status === "flagged");
      return { action: "none", say: bad.length ? "Our inspectors caught " + bad.map((a) => nice(a.id)).join(" and ") + ". They are marked with a red warning. You can still run one to watch it get caught." : "Nobody has been caught yet." };
    }
    if (has(/ (file|files|drawer|drawers|safe|private|secret|secrets|see|look at) /) && !has(/ (hire|pick|choose) /)) {
      return { action: "none", say: ctx.sees || "Open or close the drawers in the safe to choose what the helper may look at. Secret files stay locked unless you allow everything." };
    }
    if (has(/ (hire|pick|choose|get|find|want|need|select|use|me) /) || byName()) {
      const named = byName(); if (named) return pick(named, "hiring ");
      if (has(/ (cheapest|cheap|lowest|least expensive|budget) /)) { const a = usable.slice().sort((x, y) => x.price_usd - y.price_usd)[0]; if (a) return pick(a, "the cheapest is "); }
      if (has(/ (web|internet|online|look up|lookup|search|research) /)) { const a = usable.find((x) => /web/i.test(x.summary)); if (a) return pick(a, "for web research, "); }
      if (has(/ (remember|memory|suggest|notes) /)) { const a = usable.find((x) => /remember/i.test(x.summary)); if (a) return pick(a, "one that suggests things to remember is "); }
      if (has(/ (best|top|most trusted|number one|first|smartest|safest) /) || ranked.length) { if (ranked[0]) return pick(ranked[0], "the most trusted is "); }
    }
    return { action: "none", say: "I did not catch that. Try \"hire the best one\", \"hire the cheapest\", or ask about your coins." };
  }

  root.parseIntent = parseIntent; root.niceName = nice;
  if (typeof module !== "undefined") module.exports = { parseIntent, nice };
})(typeof window !== "undefined" ? window : globalThis);
