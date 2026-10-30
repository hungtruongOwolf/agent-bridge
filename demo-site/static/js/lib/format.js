/* Plain-language formatting used across the console. */

export const niceName = (id) => String(id || "").split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
export const cents = (c) => c + "¢";
export const plural = (n, one, many) => n + " " + (n === 1 ? one : many || one + "s");
export const pretty = (path) => (path ? path.split("/").map((x) => x.replace(/^./, (c) => c.toUpperCase())).join(" › ") : "Everything");

export const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");
export const day = (t) => new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
export const month = (t) => new Date(t * 1000).toLocaleDateString([], { month: "short", year: "numeric" });

/** Cut a text at `n` characters, with an ellipsis. */
export const snip = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

/** A name for a stable look: the same text always gives the same number. */
export function hash(s) {
  let h = 7;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}
