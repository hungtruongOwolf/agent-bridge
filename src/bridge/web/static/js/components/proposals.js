/* Things a helper suggests you remember. Nothing is saved unless the person says yes. Shown on My office and My memory. */
import { el, btn } from "../lib/dom.js";
import { post } from "../lib/api.js";
import { getState, refresh } from "../lib/store.js";
import { say } from "../lib/toast.js";

/** Draw the pending suggestions into `box`; returns how many there are. */
export function drawProposals(box) {
  box.replaceChildren();
  const list = getState().proposals;
  list.forEach((p) => {
    const card = el("div", "note"), acts = el("div", "acts");
    const decide = async (action) => { try { await post("/api/proposal", { id: p.id, action }); await refresh(); } catch (e) { say(e.message); } };
    acts.append(btn("Remember it", "btn", () => decide("accept")), btn("No thanks", "btn", () => decide("reject")));
    card.append(el("div", null, "“" + p.text + "”"), el("div", "muted small", "A helper suggests you remember this. It is not saved unless you say yes."), acts);
    box.append(card);
  });
  return list.length;
}
