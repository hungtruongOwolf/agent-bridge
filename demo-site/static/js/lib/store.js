/* The console's shared state: what /api/state last said. Screens read it and subscribe to changes. */
import { get } from "./api.js";

let state = null;
const listeners = new Set();

export const getState = () => state;

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Fetch the latest state and tell every subscriber. */
export async function refresh() {
  state = await get("/api/state");
  listeners.forEach((fn) => { try { fn(state); } catch (e) { console.error(e); } });
  return state;
}

/** The wording the server keeps for things a helper was stopped from doing. */
export const blocked = (kind) => (state && state.blocked_phrases && state.blocked_phrases[kind]) || undefined;
