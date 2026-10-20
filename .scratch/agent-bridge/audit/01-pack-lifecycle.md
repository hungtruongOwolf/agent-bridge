# Audit 01: Pack lifecycle (author -> validate -> certify -> sign -> publish -> install/approve -> run -> feedback -> improve -> deprecate/revoke)

Date: 2026-10-07. Subject: `architecture-v2.md` sections 3.3, 3.4, 4 (rollback), 5.1-5.5, 6.2, 7.2, 10. Only the repo documents were audited; no external facts are claimed except where marked UNVERIFIED. `architecture-v2.md` is not edited.

## 1. Actors and the state each holds

| Actor | Trust | State it holds |
|---|---|---|
| Author (A) | untrusted | author key (Ed25519), pack source tree, hub account, payout destination |
| Pack Studio CLI | A's machine | local validate/eval results, draft digest |
| Hub registry | honest-but-curious (B2) | (id, version) -> digest map, card.json, attestations, transparency log, revocation list, run-token issuer, escrow state |
| Certifier | hub | private suites, per-(digest, model) scores |
| Requester supervisor (S) | trusted (B1) | approvals, local denylist, cached revocation list, audit log, incident evidence |
| Requester vault (U/Q/P) | trusted | records with provenance, P-plane per digest |
| Cell + Sidecar | Cell untrusted, sidecar trusted | run token, Biscuit, staged snapshot |
| Nebius, PayPal | external | model calls; authorization/capture state |
| Host (Hosted) | untrusted root | packet, receipts |

## 2. Version state machine (as the document implies it; marked where the document is silent)

States (document names only: author-draft, validated, certified, signed, published, deprecated, revoked).
Missing in the document: REJECTED, SUSPENDED/ADVISORY, YANKED, EXPIRED-CERT, SUPERSEDED-BY.

```
DRAFT --validate--> VALIDATED --certify--> CERTIFIED --sign(owner+hub)--> SIGNED --publish--> PUBLISHED
   ^                    |  fail                |  fail                                          |  |  |
   |                    v                      v                                                |  |  +--> DEPRECATED (author, reversible? undefined)
   +----(edit = new digest, new lineage)--- REJECTED (undefined: appeal, resubmit limit)        |  +-----> YANKED (undefined)
                                                                                                +--------> REVOKED (terminal? reasons? undefined)
```

Observed orderings in the text: step 4 Certify precedes step 5 Sign, but the attestation is "bound to (digest, model, suite version)" and the manifest (which is inside the digest) carries `tested_on` "filled by Certifier". See finding F5.

## 3. Numbered sequence with actors and state

1. A: `pack init` (template or upstream import with pinned SHA). State: draft tree.
2. A: `pack validate` (schema, path containment, SPDX, SBOM, secret scan, pinned refs). Local only; the hub must repeat it (author machine is untrusted).
3. A: local eval (free graders, 3+ runs, baseline delta). Result is advisory.
4. A -> Hub: upload tree. Hub computes canonical digest D. Hub re-validates. Hub checks permission diff vs previous version (NOT DEFINED in v2; only "any widening is MAJOR" as a rule, not as an enforced check).
5. Hub -> Certifier: run per (D, model) in separate pack/grader sandboxes; produce score LCB, security-suite result, honeypot/cheater result. Result delivered to A with unspecified detail.
6. Sign: A signs D (Ed25519); hub countersigns the certification; both appended to the hash-chained log. Log is operated by the hub.
7. Publish: (id, version) -> D write-once (NOT DEFINED how enforced); card.json generated; account-age gate and vetting.
8. Requester discovery: agent calls hub MCP; verifies signature, log inclusion, revocation, license, tested_on, driver tier. Against which log head and which revocation list freshness: NOT DEFINED.
9. Approve: one card per (digest, mode, lens, budget). Expiry of approval: NOT DEFINED. Re-approval on version change "diff-based".
10. Run start: hub issues one-time run token + PayPal AUTHORIZE; S checks revocation; vaultd stages snapshot; Cell starts.
11. Run: planner -> worker -> returner; detectors; strikes; ladder.
12. End: Result Guard, acceptance, capture (partial/final), holdback, receipt, Q proposals, accept into U.
13. Feedback: rating bound to capture, fixed-schema receipts, opt-in bundles.
14. Improve: optimizer edits H-plane only; candidate vN+1 with parent = vN; held-out gate; re-certify; owner approves; new sign/publish (loop to 4).
15. Deprecate / revoke: signed revocation list; supervisors check "before every start and on each broker call". Incident path: S -> signed revocation proposal -> hub.

## 4. Per-step failure analysis (what-if matrix, condensed)

| Step | Fails | Repeated | Out of order | Concurrent | Timeout | Malicious actor | Offline | State changed between |
|---|---|---|---|---|---|---|---|---|
| 4 upload | partial upload -> digest of partial tree? | idempotent by digest, ok | v1.1.0 after v2.0.0 (backport) undefined | two devices publish same (id, version) with different trees: no CAS stated | n/a | A sets `parent` to a top-ranked pack; A hides widening in a MINOR | A offline fine | previous version revoked between upload and publish: parent now revoked |
| 5 certify | model removed mid-cert; no state | resubmission leaks private suite via feedback | cert done after yank of parent | same D certified on two models in parallel fine | cert never completes: stuck state undefined | pack detects Certifier and behaves | hub fleet down | suite rotated mid-run: attestation bound to which suite version |
| 6 sign | author key stolen | duplicate signatures | sign before certify possible | n/a | n/a | takeover signs malicious patch | n/a | key rotated between certify and sign |
| 7 publish | log append fails after registry write: split state | double publish | n/a | namespace race, squat | n/a | namespace re-registration after account deletion | n/a | n/a |
| 9 approve | n/a | n/a | approval for old digest used after update | one approval used by N concurrent runs: N x budget | approval has no expiry | approval-card spam / fatigue | n/a | pack revoked after approval; effective permission semantics change after engine/driver update |
| 10 start | hub unreachable | run token replay | token before AUTHORIZE | same token twice | token expires on long run | requester fabricates incident to void | requester offline from hub: stale revocation list | revocation arrives between check and Cell start |
| 11 run | Cell crash: resume? | retry re-charges? | n/a | detector firings on two runs | hold expires before capture | requester forges canary hit | hub offline mid-run: "check on each broker call" cannot happen | pack revoked mid-run |
| 12 end | capture fails after result released | double capture | accept after kill | n/a | holdback vs 180-day dispute | requester claims incident post-hoc | n/a | pack revoked after result, before promotion of Q items |
| 14 improve | candidate regresses | n/a | parent revoked | two candidates from same parent: both publish, ranking forks | n/a | optimizer poisoned by consented traces | n/a | parent's permission set changed |
| 15 revoke | list distribution fails | duplicate | un-revoke by attacker with key | revoke vs run race | n/a | competitor framing via proposals | requester offline | in-flight runs |

## 5. Consistency checks with other flows and the guarantees text

- 3.3 says "the author receives nothing during the run". Section 5.3 step 10 says supervisors check revocation "on each broker call". A per-call or per-pack lookup at the hub tells the hub (B2) which pack a requester is running and when. Contradiction unless the check is a full-list download. Update check in 3.4 ("pack id and version query") has the same issue.
- Section 5.1 digest covers the manifest, section 5.2 puts `tested_on` / `certified_digest` in that manifest "filled by Certifier". Circular.
- Section 4.5 "never delete" and "roll back U to the pre-task checkpoint" in 7.2 step 7 conflict under concurrent local writes.
- Section 6.2 "one-time run token" conflicts with the owner's new requirement of long, resumable, retried workflows.
- 7.2 "PayPal VOID ... on a deterministic CRITICAL" where the supervisor is requester-controlled in Pull conflicts with the paid-author threat model: evidence for a CRITICAL is self-produced by the party that benefits from voiding.
- 5.4 "ranking recomputable by a third party from the signed attestation log" does not provide integrity if the log operator is the hub (no consistency proofs or witnesses).

## 6. Findings

See the structured result returned with this audit (F1-F12). Short list:

1. F1 Revocation has no freshness, fail mode, or offline/in-flight semantics, and its lookup conflicts with the no-metadata guarantee.
2. F2 Requester-controlled supervisor can fabricate a CRITICAL to VOID payment after receiving the result; revocation proposals can frame authors.
3. F3 Author key takeover and rotation are undefined; stolen key ships a "patch".
4. F4 Semver and lineage are author-declared; widening is not checked by the hub or by re-approval logic.
5. F5 Digest covers fields filled after certification; attestation binds too little (engine, runner image, driver, upstream).
6. F6 One-time run token and AUTHORIZE hold do not fit resumable or long workflows.
7. F7 No TUF-style freshness: hub can freeze, roll back or split-view versions and the log.
8. F8 Missing states (yank, suspend, advisory, reasoned revocation) and no per-reason in-flight and payment behaviour.
9. F9 Upstream SHA, runner, model id and engine versions are outside the digest; no reverse-dependency revocation or cert expiry.
10. F10 Revocation does not reach memory already promoted from the revoked pack; rollback is unsafe under concurrency.
11. F11 Concurrency and naming races: (id, version) write-once, namespace squat/reuse, shared approval budget, denylist scope.
12. F12 Certification failure feedback is an oracle on the private suite; no rejected/appeal/resubmit state; canonicalization differential (CRLF, YAML) between digest, validator and D9.
