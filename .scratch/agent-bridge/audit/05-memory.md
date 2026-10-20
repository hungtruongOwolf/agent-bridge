# Audit 05: Memory flows (architecture-v2 section 4, 5.5, 6.2, 7.2)

Auditor: flow auditor, 2026-10-07. Source: architecture-v2.md only (no external facts used). F-numbers are the findings in section 4.

## 1. Actors and the state each holds

| Actor | State held |
|---|---|
| User | approvals, root key backup (recovery undefined) |
| Local agent (chat) | context window (may contain foreign text), write rights to U via Scribe |
| Capture hook | raw events (chat, tool output, files) |
| Journal (replicated) | hash-chained lines {seq, ts, actor, op, record_id, base_version, content_hash, prev_hash, sig}; Merkle checkpoints |
| Extractor (local model or approved endpoint) | raw captured text, proposals |
| vaultd write gate | CAS version per record, schema check, promotion rules |
| U store | Markdown records + front-matter, per-record key_id |
| Derived index | SQLite + embeddings (rebuildable) |
| Q | proposals from foreign sources |
| P | per-pack-digest memory (ratings, accepted outputs, quirks, strikes, lens prefs) |
| Broker / Sidecar | Biscuit, read accounting, canaries, staged snapshot (/in) |
| Supervisor | checkpoint ids, ladder, rollback authority |
| Audit log (separate hash chain) | queries, canary placement, incident evidence |
| Other devices | journal replica, device key |
| Relay / hub | ciphertext, metadata |

## 2. Flow as numbered sequence

A. Normal capture path
1. Capture hook records event E (user chat turn, tool output, file) -> journal append (actor = local-agent or user).
2. Extractor reads E (and context) -> typed proposal {type, ns, source.class, content}.
3. vaultd schema check -> promotion gate by type (auto if trusted-local or 2+ independent source classes; else human digest; foreign -> Q).
4. Record written with CAS (base_version -> version+1); journal line with content_hash; index updated.
5. Fact change: old record gets invalid_at, new record with provenance. TTL/decay later.
6. Delete: drop per-record key; journal keeps tombstone hash.

B. Pack run (Pull)
1. Supervisor takes Merkle checkpoint C0. 2. Approval of lens. 3. vaultd stages read-only snapshot of lens slice to /in with canaries/decoys. 4. Broker mints Biscuit. 5. Cell runs; memory.search via Broker (order 1-9 in 4.4). 6. Pack emits result + proposals. 7. Result Guard, acceptance. 8. Proposals -> Q. 9. Receipt, Cell destroyed. 10. On CRITICAL: kill, quarantine (keep diff, logs, memory snapshot), revoke, ladder step 7: roll back U to C0 and discard Q items from run.

C. Review
1. Daily digest of profile/procedural/secret and Q items. 2. User accepts -> record in U (tier undefined). 3. Accepted pack output becomes retrievable for later packs (cross-pack benefit).

D. Multi-device
1. Journal lines replicate over relay with per-device keys. 2. Conflicts surface to user. 3. Checkpoint before every task.

## 3. Failure matrix (condensed)

| Step | Fails | Repeated | Out of order | Concurrent | Timeout | Malicious | Offline | State changed in between |
|---|---|---|---|---|---|---|---|---|
| A2 extractor | no queue/dead-letter (F7) | duplicate proposals, no idempotency key (F7) | proposal for superseded record | two devices extract same event (F6) | approved endpoint revoked | poisoned text steers extractor (F3) | local model absent | event later shredded (F5) |
| A3 gate | Q full / digest ignored (F7) | resubmit same item | corroboration after expiry | two devices promote same proposal (F6) | digest unanswered = ? | source.class laundered (F3) | phone approval offline | source later revoked (F9) |
| A4 CAS | conflict UI undefined | retry creates dup | | CAS vs version vector disagree (F6) | | | | |
| A6 shred | key backups, replicas (F5) | | content arrives after tombstone (F6) | shred during staged run (F2) | | | offline device re-seeds (F6) | |
| B3 stage | disk full | stage twice | | edit during run (F2) | long run, stale snapshot (F2) | decoys leak (F2) | | |
| B10 rollback | partial rollback | double rollback | | concurrent user edits, concurrent runs (F1) | | attacker triggers CRITICAL to cause loss (F1) | other device | |
| C2 accept | | | | | fatigue | sensitivity laundering (F4) | | |
| D1 replicate | | | lines out of order break chain (F6) | chain fork (F6) | | stolen device (F6) | device offline | |

## 4. Findings

### F1 (high, contradiction/race). Ladder step 7 "roll back U to pre-task checkpoint" destroys legitimate concurrent work and conflicts with append-only
- Journal is append-only and hash-chained; rollback has no defined mechanics. Truncation breaks the chain for devices that already replicated later lines.
- A run can last hours. The user keeps chatting, the local agent writes episodics, the user accepts digest items, another device edits. Rollback to C0 drops all of it. Two concurrent runs each have a checkpoint; killing one rolls back state the other produced.
- Packs cannot write U (4.3, 4.7), so nothing the pack wrote exists in U to roll back. U is touched only via user or local agent. An attacker who can trigger a CRITICAL (framing via canary plus egress, a budget abuse) can cause the user data loss.
- Fix: no truncation. Rollback = compensating revert events scoped to a causal set (records whose provenance traces to the run, from Broker read accounting and Scribe lineage), applied only if per-record version still equals the tainted version; otherwise raise a conflict. Preview before apply. Reserve U revert for local-agent contamination.

### F2 (high, contradiction). Two read paths: staged /in snapshot vs Broker memory.search
- 6.2 step 4 stages the lens slice to /in; 4.4 promises snippets, budgets, slot caps, accounting, no dump. A pack reading /in has a raw dump bypassing steps 5-9 and D4 (file reads are not broker calls). Byte-exact preview is possible only for a staged snapshot, not for a query-time semantic filter.
- Staleness and shred: during a long run the user invalidates, reclassifies to secret, or shreds a record; the pack still holds it. Snapshot on VM disk persists (tmpfs UNVERIFIED on WSL2).
- Canaries/decoys "outside the lens" staged into /in: if written to U/journal they replicate and get re-extracted as real memories.
- Fix: snapshot held by the sidecar (encrypted, in memory); pack gets only Broker results; /in carries only packet-approved artifacts. Preview = lens definition plus dry-run stats. Sidecar subscribes to invalidate/shred/reclassify events and evicts. Canaries minted per run in the sidecar, never written to U or the replicated journal; only salted hashes go to the audit log.

### F3 (high, gap). Source-class laundering via extractor and normal chat
- The gate trusts source.class, set by extractor/capture. In normal chat the local agent reads web pages, documents and accepted pack output, and its turn is journalled actor=local-agent. Reader/Scribe exists for pack output, not for the everyday chat session, where one context holds foreign text and write rights.
- An injected document makes the agent "observe" a fact, stamped trusted-local, auto-promoted. The "independent second class" (user acts on it) is causally downstream of the same poison.
- Fix: taint set by the capture hook: each event carries the union of source classes of everything in context at that time; proposals inherit it; any foreign taint forces Q. Independence = disjoint ancestry computed from the journal DAG. Agent-initiated writes with foreign content in context go to Q; only explicit user "remember" is trusted.

### F4 (high, abuse). Cross-pack benefit is a sensitivity-laundering and dead-drop path
- Pack A reads medium data, quotes it in output, the user accepts into U. Default sensitivity and tier of accepted pack items is undefined; if low/tier 3, pack B with a lower ceiling or a Hosted packet (6.3 excludes only Pull-only items) receives it. A colluding author (two pack ids) plants instructions for pack B in A's output.
- Fix: label propagation: derived sensitivity = max of reads recorded in accounting for the run (floor medium). New tier "pack-derived, user-accepted" below user-authored, with its own slot cap. Not served to a different author's pack unless the lens names it; excluded from Hosted packets by default.

### F5 (high, gap). Crypto-shred leaves what matters
- Journal stores content_hash of plaintext: low-entropy content is confirmable by guess-and-hash after shred.
- Remaining: ns, lens_tags, ts, ids in journal; SQLite and embeddings (inversion); Mem0/graph store; staged snapshots; Q copies; audit log (queries, quarantine memory snapshot); replicas and relay; Nebius if extractor approved; OS backups; root-key recovery backup if it holds record keys. Encryption at rest is unspecified for "canonical Markdown", so key_id may protect nothing.
- Fix: journal stores ciphertext plus keyed commitment HMAC(record_key, content); metadata encrypted under a shreddable key; shred = signed monotone tombstone replicated everywhere, index rows deleted/rebuilt; key hierarchy where backups hold only wrapped, rotated keys; audit and quarantine have retention and shred; document non-removable residue (already sent to Nebius).

### F6 (high, race). Multi-device chain fork, CAS vs version vector, shred resurrection
- One prev_hash/seq chain forks with two offline writers; "checkpoint before every task" is ambiguous on which device; out-of-order replication breaks verification.
- 4.3 CAS vs 4.6 version vectors disagree on conflict detection. Same Q item accepted on phone and desktop duplicates (no idempotency id). Clock skew affects valid_at/invalid_at/TTL; two devices invalidate one fact with different successors.
- Offline device holds plaintext and key; on reconnect it re-replicates a shredded record. Lost device: revoking its key leaves its replica.
- Fix: per-device signed sub-chains, checkpoint = vector of heads, deterministic merge; one conflict model (VV plus conflict event, CAS local fast path); idempotent proposal ids; tombstones dominate and replicate first; hybrid logical clocks; device revocation rekeys future data and states residual risk.

### F7 (medium-high, failure-mode). Extractor failure, Q backlog, Q read by local agent
- No extraction queue, retry, dead-letter, or "unprocessed" state; events can be silently skipped, so "journal is truth" hides lost memories. Re-extraction with another model rewrites memories without history.
- Q "capped to a few slots for the local agent": the local agent holds write rights, so Q text enters the Scribe context, breaking the split. max_items 5 per run times unlimited runs floods Q and hides the bad item; expiry undefined.
- Fix: durable queue with attempts, dead-letter, extractor version per proposal; Q read only by a Reader without write tools; Scribe sees schema-validated length-capped fields; per-pack and global Q quotas, auto-expiry with notice, risk-sorted digest, batch reject by pack.

### F8 (medium-high, gap). Secrets enter journal and audit log, which are not editable
- Capture precedes typing: pasted API keys, tool env dumps reach the journal, a remote extractor, the audit log (queries, tool args, evidence) and quarantine logs. Presidio is poor at keys.
- Fix: pattern+entropy scanner at capture before append; redacted events never go to a remote extractor; secrets created only by explicit user action, referenced by handle; audit applies same redaction with shreddable per-entry keys; dereference only in Tool Broker with output scrubbing.

### F9 (high, gap). Revocation and quarantine do not reach memory already promoted
- Ladder discards Q "from that run" only. Items accepted earlier from that digest, derived facts, P entries and other packs' outputs built on them stay trusted. Sleeper packs behave for N runs then turn.
- Fix: provenance (pack digest, run id) and dependency edges on every pack-derived record; revocation demotes by provenance to Q with a diff, flags dependents, retrieval excludes revoked provenance immediately.

### F10 (medium, gap). P plane under-specified, can leak or be gamed
- Not typed in 4.2; outside journal, shred, replication, migration, rollback. Keyed by digest: republishing resets strikes. Stores "accepted outputs" (sensitive copies) and is read by the local agent (prompts to Nebius). "Aggregates only" has no enforcement point; hub queries and update checks reveal which packs and how often; auto lens tuning rewards farmed ratings.
- Fix: P = vault namespace with the same schema, journal, encryption, shred. Key by author and lineage, strikes inherit along parent. Store references, not copies. Lens widening suggest-only. No outbound request carries P-derived data; batch/cache hub queries.

### F11 (medium, undefined-behavior). Schema migration
- Using invalid_at (valid-time) for schema supersession corrupts bi-temporal queries. Mixed-version devices can rewrite records they cannot parse, dropping security labels. Rollback across a migration undefined. Broker downcast for old packs may strip provenance/sensitivity.
- Fix: separate superseded_by (system time) from invalid_at; read-time upcasters with lazy rewrite; devices refuse to write newer schemas than they know; downcast must preserve labels or pack refused; migration is a checkpointed resumable job with dry-run.

### F12 (medium, undefined-behavior). Growth and decay
- Episodic auto-writes every capture: unbounded. TTL vs "never delete" vs shred undefined. Recency decay lets an attacker flood to displace real items; tier 3 slots unbounded; index rebuild and snapshot sizes grow.
- Fix: per-type retention and summarising compaction with provenance; define TTL = hide vs shred; quotas per ns and source class; non-recency ranking features; incremental index.

## 5. Consistency notes
- 7.2 step 7 vs 4.5 append-only (F1). 6.2 step 4 vs 4.4 (F2). 4.3 Reader/Scribe vs Q read (F7). 4.2 key_id vs plaintext Markdown (F5).
- Guarantee "author receives nothing" depends on label survival (F2, F4).
- Phase 5/6 exit tests do not cover any of these; add a test per finding.
