/* Backup: download everything in memory as one file, and put a backup back. (Adding notes lives in add-dialog.js.) */
import { $ } from "../lib/dom.js";
import { get, post } from "../lib/api.js";
import { refresh } from "../lib/store.js";
import { say } from "../lib/toast.js";
import { plural } from "../lib/format.js";

const MAX_BACKUP = 380000;

function setupBackup() {
  $("memexport").onclick = async () => {
    try {
      const data = await get("/api/memory/export"), blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "my-memory-backup.json";
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      say(`Saved: a backup with ${plural(data.notes, "note")} was downloaded.`);
    } catch (e) { say(e.message); }
  };
  $("memrestore").onchange = async (ev) => {
    const f = ev.target.files[0];
    if (!f) return;
    if (f.size > MAX_BACKUP) { say("That file is too big to put back here (the limit is 380 KB)."); return; }
    try {
      const out = await post("/api/memory", { action: "restore_backup", backup: JSON.parse(await f.text()) });
      say(`Saved: ${plural(out.added, "note")} put back` + (out.skipped ? `, ${out.skipped} already here were left alone.` : "."));
      await refresh();
    } catch (e) { say(e instanceof SyntaxError ? "That file is not a backup." : e.message); }
    ev.target.value = "";
  };
}

export function setupMemoryForms() {
  setupBackup();
}
