/* How this works: five short lines, in a dialog. /help (the text itself is in index.html so it can be read without scripts). */
import { overlay } from "../lib/overlay.js";

export const helpView = overlay("help", async () => {});
