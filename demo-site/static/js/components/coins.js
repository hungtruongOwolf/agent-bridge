/* The coins chip in the top bar: what has been spent and what is on hold. Click it for every receipt. */
import { $ } from "../lib/dom.js";
import { cents } from "../lib/format.js";
import { MODE } from "../views/wallet.js";

export function drawCoins(state) {
  const w = state.payments;
  if (!w) return;
  $("coinchip").textContent = "Spent " + cents(w.captured) + (w.on_hold ? ", on hold " + cents(w.on_hold) : "");
  $("coinlabel").textContent = MODE[w.provider] ? MODE[w.provider].short : "Coins";
}
