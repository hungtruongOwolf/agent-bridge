/* The only place the console talks to the server. Every request carries the page's token; errors become plain sentences. */

const TOKEN = document.body.dataset.token;
const KNOWN = /spending limit|still working|write a message|characters|full|exist|no longer|shelf|shelves|type|text|secret|everyday|name|hold is not approved|payment service said|payment could not|not helpful|already|limit|remember|choose|file|levels|add between|plan|price|version|published|fix these/i;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function friendly(msg, status) {
  if (msg && KNOWN.test(msg) && !/digest|registered|revoked|run_id|under that id|Error/.test(msg)) return msg;
  if (status === 403) return "This page lost its permission to talk to the console. Reload the page.";
  if (status === 503) return "The payment service has not answered yet. Try again in a moment.";
  return "Something went wrong. Please try again.";
}

async function request(path, init) {
  let r;
  try {
    r = await fetch(path, init);
  } catch (e) {
    throw new ApiError("The console is not answering. Check that it is still running.", 0);
  }
  let j = {};
  try { j = await r.json(); } catch (e) { /* an empty or non-JSON body */ }
  if (!r.ok) throw new ApiError(friendly(j.error, r.status), r.status);
  return j;
}

/** GET (no body) or POST (with a body, as JSON). */
export function api(path, body) {
  const headers = { "X-Bridge-Token": TOKEN };
  if (body === undefined) return request(path, { headers });
  return request(path, { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const get = (path) => api(path);
export const post = (path, body) => api(path, body || {});

/** Build "/api/x?a=1&b=2" with every value encoded. */
export function url(path, params) {
  const q = Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v));
  return q.length ? path + "?" + q.join("&") : path;
}
