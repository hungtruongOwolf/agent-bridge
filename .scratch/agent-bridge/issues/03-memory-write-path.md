# 03 Memory write path (proposals, quarantine, accept)

Status: open
Milestone: M1

The vault becomes updatable. A pack never writes memory. After a run it may return typed proposals (id-free, schema-limited: type, short text, source run). Proposals land in a quarantine tier Q, tagged with origin (pack digest, run id) and a taint flag. Only the user can promote one: accepted items enter the vault with trust tier 1 (endorsed-foreign) and an immutable origin. Rejected and expired items are dropped. Quarantined items are never served to a pack. Reverting a run removes its quarantine items and any vault records whose origin is that run, leaving user-authored records alone.

Done when: a run returns a proposal, the console shows it in a "Review" list, accept adds it to the vault and the next run's lens can include it (marked `from pack X`), reject discards it, run revert works, and a test proves a pack-written record cannot be read back by a pack unless the user accepted it.
