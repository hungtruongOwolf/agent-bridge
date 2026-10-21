# 2. Data lives in small SQLite databases, not in JSON files rewritten whole

Status: accepted (2026-10-21)

## Context
Every change rewrote a whole JSON file: one edited note rewrote all notes, one chat message rewrote all chats, one payment
rewrote the whole ledger. The cost grew with the amount of data, a crash in the middle could lose the file, and every request
re-parsed files to see what changed.

## Decision
`storage/db.py` is a tiny document store on SQLite (WAL, one shared connection behind one lock, transactions).
- **Memory** (`vault.db`): one row per note. The notes stay in memory as the working copy; a change is made on a copy, then
  the rows that differ are written in one transaction, so a failed change leaves both memory and disk as they were.
  The trash, earlier versions and shelf notes are tables in the same database.
- **Chats** (`threads.db`): one row per chat; a message writes only its own chat.
- **Ledger** (`ledger.db`): one row per payment; only touched rows are written. Time-driven rules and payouts look only at the
  rows that can still change (`_active`), and totals are cached until a row changes.
- **Plans** (`subscriptions.db`): small, written whole.
- Older JSON files are imported once, on first start, and left in place as a backup. A starter set of notes is used only when
  nothing exists yet; an emptied memory stays empty.
- Word work (accents, stems) is cached per text, so searching and building the shelf tree stop re-doing it.

## Measured (20,000 notes)
Editing one note: about 4 ms (it rewrote the whole file before). Shelf list for a shelf: 7 ms. Rebuilding the shelf tree after
a change: about 0.3 s (once per change, not per request).

## Not done, and why
- Calls to the payment provider still happen while a lock is held. Making that per-payment is a change to the state machine's
  safety argument and needs its own review. At one person's volume it does not matter; at many buyers it will.
- Memory is one writer in one process (this console). More than one console on the same files is not supported.
- Searching notes still scans in memory (fast to 20,000 notes). Past that, an FTS index in the same database is the next step.
