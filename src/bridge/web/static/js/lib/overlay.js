/* A route that shows a dialog on top of whatever screen is underneath (a helper's profile, the wallet, the help).
   Opening the address opens the dialog; closing the dialog (button, Escape) goes back to the screen under it. */
import { $ } from "./dom.js";
import { closeOverlay } from "./nav.js";

/** render(params, body) fills `<id>body` each time the dialog opens. */
export function overlay(dialogId, render) {
  let byRouter = false;
  return {
    section: null,
    overlay: true,

    mount() {
      const dlg = $(dialogId);
      dlg.addEventListener("close", () => { if (!byRouter) closeOverlay(); byRouter = false; });
      const x = dlg.querySelector("[data-close]");
      if (x) x.onclick = () => dlg.close();
    },

    async enter(params) {
      const dlg = $(dialogId);
      if (!dlg.open) dlg.showModal();
      await render(params, $(dialogId + "body"));
    },

    leave() {
      const dlg = $(dialogId);
      if (dlg.open) { byRouter = true; dlg.close(); }
    }
  };
}
