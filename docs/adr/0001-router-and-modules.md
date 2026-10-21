# 1. The console has addresses, and the server has a router

Status: accepted (2026-10-21)

## Context
The console was one page with tab buttons and window globals, so a screen had no address: no back button, no reload, no
link to a chat or a shelf. The server was one class (`App`) that ran helpers, moved money, worded receipts and answered every
request through a hand-written `if` chain.

## Decision
- **Browser:** ES modules, no build step. `lib/router.js` maps addresses to screens (`/`, `/chats/:id`, `/helpers/:id/:tab`,
  `/memory/shelf/*path`, `/wallet` as a dialog over the page below it). Screens live in `views/`, shared parts in `components/`,
  drawing in `pixel/`, and the step editor in `studio/` with its logic in a pure file that node tests.
- **Server:** `web/api/router.py` declares each API address once (method, address, whether it needs the page's token).
  `web/routes/*.py` say which service answers which address. `web/api/transport.py` is the only place that touches sockets and
  holds every safety rule (local host only, token on changes, body limit, plain-language errors, nothing internal leaks).
  `web/services/` holds what used to be inside `App`: `RunService` (hire, run, settle) and `PaymentsService` (receipts, decisions).
  `App` in `web/server.py` only builds the parts and wires them together.
- Every screen address is also served by the server (the same page), so reload and deep links work.

## Consequences
New screen = one view file + one line in `main.js`. New API = one function + one line in a routes file.
The old `server.App`, `serve`, `make_handler` names still work.
Services take the clock, the model factory and the vault as functions, so tests can swap them after the app is built.
