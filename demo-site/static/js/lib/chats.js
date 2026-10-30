/* Starting a chat: one place, used by the helper list, the front door, the profile and the studio. */
import { post } from "./api.js";
import { refresh } from "./store.js";
import { navigate, paths } from "./nav.js";
import { toast } from "./toast.js";

/** Create a chat with a helper and walk into it. `draft` is a question to put in the message box (never sent for you). */
export async function startChat(key, draft) {
  try {
    const t = await post("/api/threads", { agent_key: key });
    await refresh();
    navigate(paths.chat(t.id) + (draft ? "?draft=" + encodeURIComponent(draft) : ""));
  } catch (e) {
    toast(e.message, true);
  }
}
