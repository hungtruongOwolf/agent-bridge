/* Cutting text into notes. Plain functions with no page in them, so they can be tested on their own. */

/** Cut a text into short notes at blank lines; a long paragraph is cut at a sentence end. */
export function splitNotes(text) {
  const out = [];
  text.replace(/\r\n/g, "\n").split(/\n\s*\n/).forEach((para) => {
    let p = para.trim().replace(/[ \t]+/g, " ");
    while (p.length > 800) {
      let cut = p.lastIndexOf(". ", 800);
      if (cut < 200) cut = p.lastIndexOf(" ", 800);
      if (cut < 200) cut = 800;
      out.push(p.slice(0, cut + 1).trim());
      p = p.slice(cut + 1).trim();
    }
    if (p) out.push(p);
  });
  return out;
}

/** Several notes pasted together: separated by blank lines if there are any, otherwise one per line. */
export function pastedNotes(text) {
  const t = text.replace(/\r\n/g, "\n").trim();
  if (!t) return [];
  return /\n\s*\n/.test(t) ? splitNotes(t) : t.split("\n").map((l) => l.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, "").trim()).filter(Boolean);
}
