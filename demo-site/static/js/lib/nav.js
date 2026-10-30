/* Navigation, for code that is not the router itself. main.js binds the router once; everything else imports these. */

let router = null;

export const bindRouter = (r) => { router = r; };
export const navigate = (path, opts) => router.navigate(path, opts);
export const closeOverlay = () => router.closeOverlay();

/** App paths, in one place, so a path is never spelled twice. */
export const paths = {
  office: () => "/",
  hire: () => "/hire",
  chat: (id) => `/chats/${encodeURIComponent(id)}`,
  helper: (key) => `/market/${encodeURIComponent(key)}`,
  studio: (id, tab) => (id ? `/helpers/${encodeURIComponent(id)}${tab && tab !== "steps" ? "/" + tab : ""}` : "/helpers"),
  memory: () => "/memory",
  shelf: (path) => (path ? "/memory/shelf/" + path.split("/").map(encodeURIComponent).join("/") : "/memory"),
  note: (id) => `/memory/note/${encodeURIComponent(id)}`,
  trash: () => "/memory/trash",
  wallet: () => "/wallet",
  help: () => "/help"
};
