/* node record.mjs <scene> [--base http://127.0.0.1:8787]
   Runs scenes/<scene>.mjs against a running console and writes video-out/rec-<scene>.mp4 (and its marks). */
import { runScene } from "./recorder.mjs";

const scene = process.argv[2];
const i = process.argv.indexOf("--base");
const base = i > 0 ? process.argv[i + 1] : "http://127.0.0.1:8787";
const mod = await import(`./scenes/${scene}.mjs`);
await runScene(scene, base, mod.default);
