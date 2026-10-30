/* A small client-side router: real URLs, back and forward, links that do not reload the page.

   A route is a path pattern with `:name` for one segment and `*name` for "the rest of the path":
       /chats/:id             /memory/shelf/*path

   The matching functions are pure (no DOM), so they are tested with node. */

export function compile(pattern) {
  const keys = [];
  const re = pattern
    .split("/")
    .map((seg) => {
      if (seg.startsWith(":")) { keys.push(seg.slice(1)); return "([^/]+)"; }
      if (seg.startsWith("*")) { keys.push(seg.slice(1)); return "(.*)"; }
      return seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  return { re: new RegExp("^" + re + "/?$"), keys };
}

export function parseQuery(search) {
  const out = {};
  new URLSearchParams(search || "").forEach((v, k) => { out[k] = v; });
  return out;
}

/** Find the first route whose pattern matches `path`. Returns {route, params} or null. */
export function match(routes, path) {
  for (const route of routes) {
    const c = route.compiled || (route.compiled = compile(route.path));
    const m = c.re.exec(path);
    if (m) {
      const params = {};
      c.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); });
      return { route, params };
    }
  }
  return null;
}

/** Build a path from a pattern and values: href("/chats/:id", {id: "t_1"}) -> "/chats/t_1" */
export function href(pattern, params) {
  return pattern.replace(/[:*]([A-Za-z_]+)/g, (_, k) => (pattern.includes("*" + k) ? String(params[k]).split("/").map(encodeURIComponent).join("/") : encodeURIComponent(params[k])));
}

/** Is this an in-app link we should handle (same origin, a plain left click, not a download or new tab)? */
export function isInternalClick(e, a, origin) {
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
  if (a.target && a.target !== "_self") return false;
  if (a.hasAttribute("download")) return false;
  const u = new URL(a.href, origin);
  return u.origin === origin && !u.pathname.startsWith("/api/") && !u.pathname.startsWith("/static/") && !u.pathname.startsWith("/paypal/");
}

export class Router {
  /** routes: [{path, name, title?, overlay?}]; onRoute(match, query, {initial}) is called on every change. */
  constructor(routes, onRoute) {
    this.routes = routes;
    this.onRoute = onRoute;
    this.base = "/";  // the last non-overlay path: where a closed dialog returns to
  }

  start() {
    window.addEventListener("popstate", () => this.render(false));
    document.addEventListener("click", (e) => {
      const a = e.target.closest && e.target.closest("a[href]");
      if (a && isInternalClick(e, a, location.origin)) {
        e.preventDefault();
        this.navigate(a.pathname + a.search);
      }
    });
    this.render(true);
  }

  navigate(path, { replace = false } = {}) {
    if (path === location.pathname + location.search) return this.render(false);
    history[replace ? "replaceState" : "pushState"]({}, "", path);
    this.render(false);
  }

  /** Close an overlay (a dialog route): go back to the screen underneath. */
  closeOverlay() {
    this.navigate(this.base, { replace: false });
  }

  render(initial) {
    const m = match(this.routes, location.pathname) || match(this.routes, "/404");
    if (!m.route.overlay) this.base = location.pathname + location.search;
    this.onRoute(m, parseQuery(location.search), { initial });
  }
}
